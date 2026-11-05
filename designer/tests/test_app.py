"""Run from the designer folder: python -m pytest"""
import copy
import http.server
import io
import json
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import pytest
import yaml

DESIGNER = Path(__file__).parent.parent
sys.path.insert(0, str(DESIGNER))

import app as app_module  # noqa: E402
import yamlgen  # noqa: E402

SEED = yamlgen.upgrade(json.loads((DESIGNER / "default_design.json").read_text(encoding="utf-8")))
CROWPANEL = yamlgen.upgrade(json.loads((DESIGNER / "default_crowpanel_7.json").read_text(encoding="utf-8")))
DEPLOYED = (DESIGNER.parent / "ha-panel-35.yaml").read_text(encoding="utf-8")
FAKE_SECRETS = (
    'wifi_ssid: "test"\nwifi_password: "testtest"\n'
    'api_encryption_key: "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="\n'  # dummy, test only
)


@pytest.fixture
def client(tmp_path):
    return app_module.create_app(tmp_path).test_client()


class Loader(yaml.SafeLoader):
    pass


Loader.add_multi_constructor("!", lambda loader, tag, node: f"{tag} {loader.construct_scalar(node)}")


def normalise(text):
    """Expand substitutions and styles so two configs compare by what they do, not how they're written."""
    subs = yaml.load(text, Loader)["substitutions"]
    for key, value in subs.items():
        if not value.startswith("${"):
            text = text.replace("${" + key + "}", str(value))
    config = yaml.load(text, Loader)
    config.pop("substitutions")
    lvgl = config["lvgl"]
    styles = {s["id"]: {k: v for k, v in s.items() if k != "id"} for s in lvgl.pop("style_definitions")}

    def expand(widgets):
        for wrapper in widgets:
            widget = next(iter(wrapper.values()))
            if "styles" in widget:
                widget.update({**styles[widget.pop("styles")], **widget})
            expand(widget.get("widgets", []))

    for page in lvgl["pages"]:
        expand(page["widgets"])
    for font in config["font"]:
        font["glyphs"] = sorted(font["glyphs"])
    config["font"] = sorted(config["font"], key=lambda f: f["id"])
    return config


def test_routes_return_200(client):
    assert client.get("/").status_code == 200
    assert client.get("/healthz").status_code == 200
    assert client.get("/api/designs/1").get_json()["device"]["name"] == "ha-panel-35"
    assert client.get("/api/designs").get_json()[0]["display"] == "waveshare_35"
    assert client.get("/api/displays").get_json()["crowpanel_7"]["width"] == 800
    assert client.get("/static/vendor/fonts/oswald-latin-700-normal.woff2").status_code == 200
    assert client.get("/static/vendor/mdi/icons.json").status_code == 200


def test_design_saves_and_survives_restart(tmp_path):
    client = app_module.create_app(tmp_path).test_client()
    design = copy.deepcopy(SEED)
    design["pages"][0]["elements"][3]["x"] = 99
    assert client.put("/api/designs/1", json=design).status_code == 200
    reopened = app_module.create_app(tmp_path).test_client()
    assert reopened.get("/api/designs/1").get_json()["pages"][0]["elements"][3]["x"] == 99


def test_save_rejects_non_design(client):
    assert client.put("/api/designs/1", json=[1, 2]).status_code == 400


def test_designs_can_be_added_and_removed(client):
    assert client.post("/api/designs", json={"display": "nonsense"}).status_code == 400
    new_id = client.post("/api/designs", json={"display": "crowpanel_7"}).get_json()["id"]
    assert client.get(f"/api/designs/{new_id}").get_json()["display"] == "crowpanel_7"
    assert [d["display"] for d in client.get("/api/designs").get_json()] == ["waveshare_35", "crowpanel_7"]
    assert client.delete(f"/api/designs/{new_id}").status_code == 200
    assert client.get(f"/api/designs/{new_id}").status_code == 404
    assert client.delete("/api/designs/1").status_code == 400  # the last one has to stay


def test_designs_saved_before_these_settings_still_work():
    """Your saved panel comes from the older format: it must load and generate unchanged."""
    old = json.loads((DESIGNER / "default_design.json").read_text(encoding="utf-8"))
    edited = old["pages"][0]["elements"][3]
    edited["x"] = 99
    upgraded = yamlgen.upgrade(copy.deepcopy(old))
    assert upgraded["display"] == "waveshare_35"
    assert upgraded["pages"][0]["elements"][3]["x"] == 99
    assert yamlgen.validate(upgraded) == []
    # Only adds keys
    for key, value in edited.items():
        assert upgraded["pages"][0]["elements"][3][key] == value


def test_default_design_reproduces_deployed_panel():
    """The designer must open with the panel you have, and output it unchanged."""
    assert yamlgen.validate(SEED) == []
    deployed = DEPLOYED.replace("ha_temperature", "ha_temp")
    assert normalise(yamlgen.generate(SEED)) == normalise(deployed)


def test_yaml_route_reports_problems(client):
    design = copy.deepcopy(SEED)
    design["pages"][0]["elements"][3]["entity"] = "not an entity"
    response = client.post("/api/yaml", json=design)
    assert response.status_code == 400
    assert any("entity" in e for e in response.get_json()["errors"])
    assert "lvgl:" in client.post("/api/yaml", json=SEED).get_json()["yaml"]


@pytest.mark.parametrize("key,bad", [
    ("text", 'x"\n  evil: true'),      # YAML injection
    ("text", "${name}"),               # ESPHome substitution
    ("text", "back\\slash"),
    ("entity", "light.x\nevil: 1"),
    ("bg", "red"),
    ("x", "16\nevil: 1"),
    ("w", 9999),
    ("align", "NOPE"),
    ("icon", "not-an-icon"),
    ("show_state", "yes"),
    ("font", "comic_sans"),
    ("off_opacity", 101),
    ("shadow_width", -1),
    ("shadow_color", "black"),
    ("x", 1000),                       # within twice the 7 inch screen, not this one
    ("w", 1000),
    ("text_size", 7),
    ("text_size", 121),
    ("icon_size", 241),
    ("icon_size", 16.5),
])
def test_validation_rejects_bad_values(key, bad):
    design = copy.deepcopy(SEED)
    design["pages"][0]["elements"][3][key] = bad
    assert yamlgen.validate(design)


def test_validation_catches_structural_problems():
    design = copy.deepcopy(SEED)
    design["pages"][0]["elements"][4]["id"] = design["pages"][0]["elements"][3]["id"]
    assert any("duplicate" in e for e in yamlgen.validate(design))

    design = copy.deepcopy(SEED)
    design["pages"] = design["pages"][:1]  # go_status now points nowhere
    assert any("doesn't exist" in e for e in yamlgen.validate(design))

    assert yamlgen.validate({"device": SEED["device"], "pages": []})
    assert yamlgen.validate("nonsense")


def test_off_opacity_and_shadow_reach_the_yaml():
    design = copy.deepcopy(SEED)
    tv = design["pages"][0]["elements"][3]
    tv.update(off_opacity=40, shadow_width=12, shadow_color="#112233", shadow_opa=60, shadow_offset_y=5)
    door = design["pages"][1]["elements"][3]
    door["off_opacity"] = 30
    assert yamlgen.validate(design) == []
    config = yaml.load(yamlgen.generate(design), Loader)
    widgets = config["lvgl"]["pages"][0]["widgets"]
    button = next(w["button"] for w in widgets if w.get("button", {}).get("id") == "btn_tv")
    assert button["opa"] == "40%" and button["checked"]["opa"] == "100%"
    assert button["shadow_width"] == 12 and button["shadow_color"] == 0x112233 and button["shadow_offset_y"] == 5
    door_sensor = next(s for s in config["text_sensor"] if s["id"] == "ha_door")
    assert "opa" in door_sensor["on_value"][0]["if"]["else"][0]["lvgl.widget.update"]


def test_wifi_icon_size_gets_its_own_font():
    design = copy.deepcopy(SEED)
    design["pages"][0]["elements"][1]["icon_size"] = 48
    config = yaml.load(yamlgen.generate(design), Loader)
    wifi_font = next(f for f in config["font"] if f["id"] == "icons_48")
    assert chr(0xF05A9) in wifi_font["glyphs"] and chr(0xF05AA) in wifi_font["glyphs"]


def custom_sizes():
    """Sizes outside the old lists, on elements running past the screen edge."""
    design = copy.deepcopy(SEED)
    elements = design["pages"][0]["elements"]
    elements[1]["icon_size"] = 28
    elements[2].update(text_size=17, chevron="right")
    elements[3].update(icon_size=50, text_size=19, x=-100, y=300, w=900)
    design["pages"][1]["elements"][4].update(value_size=33)
    return design


def test_sizes_are_free_and_only_missing_montserrat_sizes_download():
    design = custom_sizes()
    assert yamlgen.validate(design) == []
    text = yamlgen.generate(design)
    config = yaml.load(text, Loader)
    fonts = {f["id"]: f for f in config["font"]}
    assert {"icons_28", "icons_50"} <= fonts.keys()
    assert {"montserrat_17", "montserrat_19", "montserrat_33"} <= fonts.keys()
    assert fonts["montserrat_17"]["file"] == "gfonts://Montserrat@400"
    assert not {i for i in fonts if i in ("montserrat_14", "montserrat_16")}
    # Downloaded Montserrat has no LVGL arrow symbols
    assert "Home Status \u203a" in text


def test_default_design_still_uses_built_in_montserrat():
    config = yaml.load(yamlgen.generate(SEED), Loader)
    assert not [f for f in config["font"] if f["id"].startswith("montserrat")]


def test_list_order_sets_the_panel_drawing_order():
    design = copy.deepcopy(SEED)
    elements = design["pages"][0]["elements"]
    elements[3], elements[4] = elements[4], elements[3]
    text = yamlgen.generate(design)
    assert elements[3]["id"] == "table"
    assert text.index("id: btn_table") < text.index("id: btn_tv")


def test_custom_fonts_are_declared_once_with_extra_characters():
    design = copy.deepcopy(SEED)
    temp = design["pages"][1]["elements"][4]
    temp.update(font="roboto", text_size=18, value_size=30)
    button = design["pages"][0]["elements"][2]
    button.update(font="oswald_bold")
    assert yamlgen.validate(design) == []
    text = yamlgen.generate(design)
    config = yaml.load(text, Loader)
    fonts = {f["id"]: f for f in config["font"]}
    assert fonts["roboto_30"]["file"] == "gfonts://Roboto@400"
    assert "\u00b0" in fonts["roboto_30"]["glyphs"]  # the degree sign in the unit
    assert "\u203a" in fonts["oswald_bold_16"]["glyphs"]  # the page button's arrow
    assert "\uF054" not in text and "\\uF054" not in text  # that symbol only exists in Montserrat


def test_crowpanel_uses_its_own_hardware():
    assert yamlgen.validate(CROWPANEL) == []
    config = yaml.load(yamlgen.generate(CROWPANEL), Loader)
    assert config["esp32"]["board"] == "esp32-s3-devkitc-1"
    assert config["psram"]["mode"] == "octal"
    assert config["display"][0]["platform"] == "mipi_rgb" and config["display"][0]["de_pin"] == "GPIO41"
    assert config["touchscreen"][0]["platform"] == "gt911"
    assert "rotation" not in config["lvgl"] and "buffer_size" not in config["lvgl"]
    assert "spi" not in config


def test_percent_unit_is_escaped_for_printf():
    design = copy.deepcopy(SEED)
    temp = design["pages"][1]["elements"][4]
    temp["unit"] = "%"
    assert yamlgen.validate(design) == []
    assert 'format: "%.1f%%"' in yamlgen.generate(design)


def test_apostrophes_stay_valid_in_lambdas():
    design = copy.deepcopy(SEED)
    design["pages"][1]["elements"][3]["off_text"] = "Dad's open"
    assert yamlgen.validate(design) == []
    config = yaml.load(yamlgen.generate(design), Loader)
    assert any("Dad's open" in json.dumps(s) for s in config["text_sensor"])


def test_empty_sections_are_left_out():
    design = copy.deepcopy(SEED)
    design["pages"] = [{"id": "only", "name": "Only", "bg": "#000000", "elements": []}]
    assert yamlgen.validate(design) == []
    config = yaml.load(yamlgen.generate(design), Loader)
    for section in ("text_sensor", "sensor", "interval", "font"):
        assert section not in config


def test_every_icon_codepoint_becomes_a_valid_yaml_glyph():
    """Older icons have 4-digit codepoints; both lengths must give one character."""
    design = copy.deepcopy(SEED)
    short = next(name for name, code in yamlgen.ICONS.items() if len(code) == 4)
    design["pages"][0]["elements"][3]["icon"] = short
    config = yaml.load(yamlgen.generate(design), Loader)
    glyphs = {g for font in config["font"] for g in font["glyphs"]}
    assert chr(int(yamlgen.ICONS[short], 16)) in glyphs
    assert all(len(g) == 1 for g in glyphs)


PNG = b"\x89PNG\r\n\x1a\n" + (
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\rIDATx\x9cc\xf8\xcf\xc0\xf0\x1f\x00\x05\x00\x01\xff\x89\x99=\x1d"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


def add_extras(design, src):
    """Add a slider and an image to the design's first page."""
    design["pages"][0]["elements"] += [
        {"id": "dimmer", "type": "slider", "align": "TOP_LEFT", "x": 10, "y": 10, "w": 200, "h": 24,
         "entity": "light.living_room_lamps", "bg": "#3B4252", "bar_color": "#F2CF66", "knob_color": "#E4E8F0"},
        {"id": "logo", "type": "image", "align": "CENTER", "x": 0, "y": 0, "w": 64, "h": 48, "src": src},
    ]
    return design


def test_images_upload_and_are_served(client):
    created = client.post("/api/images", data=PNG, content_type="image/png")
    assert created.status_code == 201
    served = client.get(f"/images/{created.get_json()['src']}")
    assert served.data == PNG and served.mimetype == "image/png"
    assert served.headers["X-Content-Type-Options"] == "nosniff"
    assert "img-src 'self'" in served.headers["Content-Security-Policy"]


@pytest.mark.parametrize("data,content_type,status", [
    (b"<svg onload='alert(1)'/>", "image/svg+xml", 415),
    (PNG, "application/x-www-form-urlencoded", 415),  # what a cross-site form could send
    (b"not a png", "image/png", 400),
    (PNG + b"x" * app_module.MAX_IMAGE_BYTES, "image/png", 413),
])
def test_bad_images_are_rejected(client, data, content_type, status):
    assert client.post("/api/images", data=data, content_type=content_type).status_code == status


def test_image_route_stays_inside_its_folder(client):
    assert client.get("/images/..%2Fswpanel.db").status_code == 404


def test_slider_and_image_reach_the_yaml(client):
    src = client.post("/api/images", data=PNG, content_type="image/png").get_json()["src"]
    design = add_extras(copy.deepcopy(SEED), src)
    assert yamlgen.validate(design) == []
    config = yaml.load(client.post("/api/yaml", json=design, base_url="http://panel.lan:8095").get_json()["yaml"], Loader)
    widgets = config["lvgl"]["pages"][0]["widgets"]
    slider = next(w["slider"] for w in widgets if "slider" in w)
    assert slider["max_value"] == 255
    action = slider["on_release"][0]["homeassistant.action"]
    assert action["action"] == "light.turn_on" and action["data"]["entity_id"] == "light.living_room_lamps"
    assert next(s for s in config["sensor"] if s["id"] == "ha_dimmer")["attribute"] == "brightness"
    image = next(w["image"] for w in widgets if "image" in w)
    entry = config["image"][0]
    assert image["src"] == entry["id"] and entry["file"] == f"http://panel.lan:8095/images/{src}"
    assert entry["resize"] == "64x48" and entry["transparency"] == "alpha_channel"


def test_public_url_overrides_the_browser_address(client, monkeypatch):
    monkeypatch.setenv("PUBLIC_URL", "https://panel.example/")
    src = client.post("/api/images", data=PNG, content_type="image/png").get_json()["src"]
    text = client.post("/api/yaml", json=add_extras(copy.deepcopy(SEED), src)).get_json()["yaml"]
    assert f'file: "https://panel.example/images/{src}"' in text


@pytest.mark.parametrize("change", [
    {"type": "slider", "entity": "switch.not_a_light"},
    {"type": "image", "src": "../../etc/passwd"},
    {"type": "image", "src": "0123456789abcdef.svg"},
])
def test_validation_rejects_bad_sliders_and_images(change):
    design = add_extras(copy.deepcopy(SEED), "0123456789abcdef.png")
    next(e for e in design["pages"][0]["elements"] if e["type"] == change["type"]).update(change)
    assert yamlgen.validate(design)


def addon_client(tmp_path, monkeypatch, options=None):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "supervisor-token")
    if options:
        (tmp_path / "options.json").write_text(json.dumps(options), encoding="utf-8")
    return app_module.create_app(tmp_path).test_client()


INGRESS = {"REMOTE_ADDR": app_module.INGRESS_PEER}


def test_addon_only_answers_ingress_apart_from_images_and_health(tmp_path, monkeypatch):
    client = addon_client(tmp_path, monkeypatch)
    (tmp_path / "images" / "a.png").write_bytes(b"png")
    assert client.get("/", environ_base=INGRESS).status_code == 200
    assert client.get("/").status_code == 403
    assert client.get("/api/designs").status_code == 403
    # A faked header must not get past the check
    assert client.get("/", headers={"X-Forwarded-For": app_module.INGRESS_PEER}).status_code == 403
    assert client.get("/healthz").status_code == 200
    assert client.get("/images/a.png").status_code == 200


def test_only_the_addon_can_be_framed(tmp_path, monkeypatch):
    plain = app_module.create_app(tmp_path).test_client().get("/")
    assert "frame-ancestors 'none'" in plain.headers["Content-Security-Policy"]
    framed = addon_client(tmp_path, monkeypatch).get("/", environ_base=INGRESS)
    assert "frame-ancestors 'self'" in framed.headers["Content-Security-Policy"]


def test_page_uses_relative_urls_so_ingress_can_serve_it(client):
    page = client.get("/").get_data(as_text=True)
    assert 'href="static/app.css"' in page and 'src="static/app.js"' in page


def image_address(client):
    src = client.post("/api/images", data=PNG, content_type="image/png", environ_base=INGRESS).get_json()["src"]
    design = add_extras(copy.deepcopy(SEED), src)
    text = client.post("/api/yaml", json=design, environ_base=INGRESS).get_json()["yaml"]
    return re.search(rf'file: "(\S+)/images/{src}"', text).group(1)


def test_addon_images_use_its_internal_address(tmp_path, monkeypatch):
    monkeypatch.delenv("PUBLIC_URL", raising=False)
    monkeypatch.setattr(app_module.socket, "gethostname", lambda: "local-swpanel")
    assert image_address(addon_client(tmp_path, monkeypatch)) == "http://local-swpanel:8095"


def test_addon_option_overrides_the_image_address(tmp_path, monkeypatch):
    monkeypatch.delenv("PUBLIC_URL", raising=False)
    client = addon_client(tmp_path, monkeypatch, {"public_url": "http://ha.lan:8095"})
    assert image_address(client) == "http://ha.lan:8095"


def test_addon_looks_up_entities_with_the_supervisor_token(tmp_path, monkeypatch):
    client = addon_client(tmp_path, monkeypatch)
    seen = {}

    def fake_urlopen(call, timeout):
        seen.update(url=call.full_url, auth=call.get_header("Authorization"))
        return io.BytesIO(b'[{"entity_id": "light.a", "attributes": {"friendly_name": "A"}}]')

    monkeypatch.setattr(app_module.urllib.request, "urlopen", fake_urlopen)
    body = client.get("/api/ha/entities", environ_base=INGRESS).get_json()
    assert [e["id"] for e in body["entities"]] == ["light.a"]
    assert seen == {"url": "http://supervisor/core/api/states", "auth": "Bearer supervisor-token"}


def test_addon_config_matches_the_image():
    config = yaml.safe_load((DESIGNER / "config.yaml").read_text(encoding="utf-8"))
    assert isinstance(config["version"], str) and config["slug"] == "swpanel"
    assert {"aarch64", "amd64"} == set(config["arch"])
    assert f"PORT={config['ingress_port']}" in (DESIGNER / "Dockerfile").read_text(encoding="utf-8")


def test_entities_need_setting_up(client, monkeypatch):
    monkeypatch.delenv("HA_URL", raising=False)
    monkeypatch.delenv("HA_TOKEN", raising=False)
    assert client.get("/api/ha/entities").get_json() == {"configured": False, "entities": []}


def test_entities_come_from_home_assistant_without_the_token(client, monkeypatch):
    monkeypatch.setenv("HA_URL", "http://ha.lan:8123/")
    monkeypatch.setenv("HA_TOKEN", "test-token")
    seen = {}

    def fake_urlopen(call, timeout):
        seen.update(url=call.full_url, auth=call.get_header("Authorization"))
        return io.BytesIO(json.dumps([
            {"entity_id": "switch.b", "state": "on", "attributes": {}},
            {"entity_id": "light.a", "state": "on", "attributes": {"friendly_name": "A", "brightness": 128, "secret": "x"}},
        ]).encode())

    monkeypatch.setattr(app_module.urllib.request, "urlopen", fake_urlopen)
    response = client.get("/api/ha/entities")
    assert seen == {"url": "http://ha.lan:8123/api/states", "auth": "Bearer test-token"}
    assert response.get_json()["entities"] == [{"id": "light.a", "name": "A", "state": "on", "brightness": 128},
                                               {"id": "switch.b", "name": "", "state": "on", "brightness": None}]
    assert b"test-token" not in response.data and b"secret" not in response.data


@pytest.mark.parametrize("failure", [OSError("down"), io.BytesIO(b"not json"), io.BytesIO(b'{"message": "hi"}')])
def test_entities_report_when_home_assistant_fails(client, monkeypatch, failure):
    monkeypatch.setenv("HA_URL", "http://ha.lan:8123")
    monkeypatch.setenv("HA_TOKEN", "test-token")

    def fake_urlopen(call, timeout):
        if isinstance(failure, Exception):
            raise failure
        return failure

    monkeypatch.setattr(app_module.urllib.request, "urlopen", fake_urlopen)
    response = client.get("/api/ha/entities")
    assert response.status_code == 502 and response.get_json()["entities"] == []


def test_shadow_presets_are_all_valid():
    presets = json.loads((DESIGNER / "static/shadow_presets.json").read_text(encoding="utf-8"))
    assert len(presets) == 92
    design = copy.deepcopy(SEED)
    tile = design["pages"][0]["elements"][3]
    for _, _, width, colour, opacity, x, y, spread in presets:
        tile.update(shadow_width=width, shadow_color=colour, shadow_opa=opacity,
                    shadow_offset_x=x, shadow_offset_y=y, shadow_spread=spread)
        assert yamlgen.validate(design) == []


def customised():
    """The default design with every optional setting changed, so all the template's branches run."""
    design = copy.deepcopy(SEED)
    for page in design["pages"]:
        page["bg"] = "#102030"
        for e in page["elements"]:
            for key in e:
                if key in yamlgen.RULES and yamlgen.RULES[key] is yamlgen._COLOUR_RULE:
                    e[key] = "#ABCDEF"
            if "radius" in e:
                e["radius"] = 3
            if "h" in e:
                e["h"] = 60
    temp = design["pages"][1]["elements"][4]
    temp.update(unit="%", decimals=0, icon_size=48, value_size=32, font="inter", shadow_width=10)
    door = design["pages"][1]["elements"][3]
    door.update(off_text="Dad's open", off_opacity=40, font="poppins_bold")
    design["pages"][0]["elements"][3].update(off_opacity=50, shadow_width=8, font="oswald", shadow_spread=-5)
    design["pages"][0]["elements"][1]["icon_size"] = 40
    design["pages"].append({"id": "empty", "name": "Empty", "bg": "#000000", "elements": []})
    return design


@pytest.mark.skipif(not shutil.which("esphome"), reason="esphome is not installed")
@pytest.mark.parametrize("design", [SEED, customised(), custom_sizes(), CROWPANEL],
                         ids=["default", "customised", "custom_sizes", "crowpanel"])
def test_esphome_accepts_the_output(tmp_path, design):
    assert yamlgen.validate(design) == []
    (tmp_path / "secrets.yaml").write_text(FAKE_SECRETS)
    target = tmp_path / "panel.yaml"
    target.write_text(yamlgen.generate(design), encoding="utf-8")
    result = subprocess.run(["esphome", "config", str(target)], capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr + result.stdout


@pytest.mark.skipif(not shutil.which("esphome"), reason="esphome is not installed")
def test_esphome_accepts_sliders_and_downloads_images(tmp_path):
    """Uses a real web server, as that's how ESPHome gets the file from the designer."""
    served = tmp_path / "www"
    (served / "images").mkdir(parents=True)
    (served / "images" / "0123456789abcdef.png").write_bytes(PNG)
    handler = lambda *args: http.server.SimpleHTTPRequestHandler(*args, directory=served)  # noqa: E731
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    design = add_extras(copy.deepcopy(SEED), "0123456789abcdef.png")
    assert yamlgen.validate(design) == []
    (tmp_path / "secrets.yaml").write_text(FAKE_SECRETS)
    target = tmp_path / "panel.yaml"
    target.write_text(yamlgen.generate(design, f"http://127.0.0.1:{server.server_port}"), encoding="utf-8")
    result = subprocess.run(["esphome", "config", str(target)], capture_output=True, text=True, encoding="utf-8")
    server.shutdown()
    assert result.returncode == 0, result.stderr + result.stdout
    assert "deprecated" not in result.stderr + result.stdout
