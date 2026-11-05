"""Turn a saved panel design into a complete ESPHome YAML file."""
import json
import math
import re
from pathlib import Path

import jinja2

HERE = Path(__file__).parent
ICONS = json.loads((HERE / "static/vendor/mdi/icons.json").read_text())

# Colours the fixed LVGL theme already applies. An element only gets its own
# colour in the YAML when it differs from these.
THEME = {
    "bg": "#1E222B", "tile": "#2F3542", "border": "#3B4252", "tile_on": "#4A5572",
    "tile_pressed": "#3A4152", "icon": "#D8DCE4", "yellow": "#F2CF66", "muted": "#8F98AA",
    "green": "#6BCB77", "red": "#E06C75", "radius": 12,
}
ALIGNS = {"TOP_LEFT", "TOP_MID", "TOP_RIGHT", "LEFT_MID", "CENTER", "RIGHT_MID",
          "BOTTOM_LEFT", "BOTTOM_MID", "BOTTOM_RIGHT"}
# ESPHome has Montserrat built in at these sizes. Any other size is downloaded like the other fonts.
BUILT_IN_MONTSERRAT = set(range(10, 50, 2))
DISPLAYS = {
    "waveshare_35": {"label": "Waveshare 3.5inch RPi LCD (A), ESP32", "width": 480, "height": 320},
    "crowpanel_7": {"label": "Elecrow CrowPanel 7.0 inch (DIS08070H), ESP32-S3", "width": 800, "height": 480},
}
# Family and weight on Google Fonts.
FONTS = {
    "montserrat": ("Montserrat", 400),
    "roboto": ("Roboto", 400), "roboto_bold": ("Roboto", 700),
    "inter": ("Inter", 400), "inter_bold": ("Inter", 700),
    "poppins": ("Poppins", 400), "poppins_bold": ("Poppins", 700),
    "oswald": ("Oswald", 400), "oswald_bold": ("Oswald", 700),
}
# Added to designs saved before these settings existed. A width of 0 means no shadow.
_SHADOW_DEFAULTS = {"shadow_width": 0, "shadow_color": "#000000", "shadow_opa": 50,
                    "shadow_offset_x": 0, "shadow_offset_y": 4, "shadow_spread": 0}

_SLUG = re.compile(r"[a-z][a-z0-9_]{0,30}")
_ENTITY = re.compile(r"[a-z_]+\.[a-z0-9_]+")
_COLOUR = re.compile(r"#[0-9A-Fa-f]{6}")
_IMAGE = re.compile(r"[0-9a-f]{16}\.(png|jpg)")
# Text ends up inside YAML strings and C++ lambdas. These characters would need
# escaping in one or the other ($ also triggers ESPHome substitutions).
_BAD_TEXT = re.compile(r'["\\$\x00-\x1f]')


def _int(low, high):
    def check(v):
        return isinstance(v, int) and not isinstance(v, bool) and low <= v <= high
    return check, f"must be a whole number from {low} to {high}"


def _text(v):
    return isinstance(v, str) and not _BAD_TEXT.search(v)


_TEXT_RULE = (_text, 'can\'t contain ", \\, $ or line breaks')
_REQUIRED_TEXT_RULE = (lambda v: _text(v) and v.strip() != "", 'needs text, without ", \\ or $')
_COLOUR_RULE = (lambda v: isinstance(v, str) and _COLOUR.fullmatch(v), "must be a colour like #2F3542")
_ICON_RULE = (lambda v: v in ICONS, "isn't a known icon")
_SIZE_RULE = _int(8, 120)
_ENTITY_RULE = (lambda v: isinstance(v, str) and _ENTITY.fullmatch(v), "must be an entity ID like light.kitchen")

RULES = {
    # The largest display, doubled. _validate_element then checks against the design's own display.
    "x": _int(-1600, 1600), "y": _int(-960, 960), "w": _int(10, 1600), "h": _int(10, 960),
    "radius": _int(0, 240), "decimals": _int(0, 3),
    "off_opacity": _int(0, 100), "shadow_width": _int(0, 100), "shadow_opa": _int(0, 100),
    "shadow_offset_x": _int(-100, 100), "shadow_offset_y": _int(-100, 100), "shadow_spread": _int(-50, 50),
    "font": (lambda v: v in FONTS, "isn't a known font"),
    "align": (lambda v: v in ALIGNS, "isn't a known alignment"),
    "text": _REQUIRED_TEXT_RULE, "unit": _TEXT_RULE,
    "on_text": _REQUIRED_TEXT_RULE, "off_text": _REQUIRED_TEXT_RULE,
    "on_state": _REQUIRED_TEXT_RULE, "off_state": _REQUIRED_TEXT_RULE,
    "text_size": _SIZE_RULE, "value_size": _SIZE_RULE,
    "icon_size": _int(8, 240),
    "icon": _ICON_RULE, "on_icon": _ICON_RULE, "off_icon": _ICON_RULE,
    "entity": _ENTITY_RULE,
    "show_state": (lambda v: isinstance(v, bool), "must be true or false"),
    "chevron": (lambda v: v in {"none", "left", "right"}, "must be none, left or right"),
    "target": (lambda v: isinstance(v, str) and _SLUG.fullmatch(v), "must be a page"),
    "src": (lambda v: isinstance(v, str) and _IMAGE.fullmatch(v), "must be an uploaded image"),
}
for _key in ("bg", "bg_on", "border", "text_color", "icon_color", "icon_color_on",
             "value_color", "on_color", "off_color", "shadow_color", "bar_color", "knob_color"):
    RULES[_key] = _COLOUR_RULE

_BOX = ("w", "h", "radius", "bg", "border", *_SHADOW_DEFAULTS)
_TEXT = ("text_size", "text_color", "font")
REQUIRED = {
    "label": ("text", *_TEXT),
    "icon": ("icon", "icon_size", "icon_color"),
    "wifi": ("icon_size",),
    "conn": _TEXT,
    "page_button": (*_BOX, "text", *_TEXT, "chevron", "target"),
    "toggle": (*_BOX, "text", *_TEXT, "icon", "icon_size", "entity",
               "show_state", "bg_on", "icon_color", "icon_color_on", "off_opacity"),
    "sensor": (*_BOX, "text", *_TEXT, "icon", "icon_size", "icon_color",
               "entity", "unit", "decimals", "value_size", "value_color"),
    "status": (*_BOX, "text", *_TEXT, "icon_size", "entity", "off_opacity",
               "on_state", "on_text", "on_icon", "on_color",
               "off_state", "off_text", "off_icon", "off_color"),
    "slider": ("w", "h", "entity", "bg", "bar_color", "knob_color"),
    "image": ("w", "h", "src"),
}


def upgrade(design):
    """Fill in settings newer than the saved design. Only adds keys; never changes existing values."""
    if not isinstance(design, dict):
        return design
    design.setdefault("display", "waveshare_35")
    pages = design.get("pages")
    for page in pages if isinstance(pages, list) else []:
        elements = page.get("elements") if isinstance(page, dict) else None
        for e in elements if isinstance(elements, list) else []:
            if not isinstance(e, dict):
                continue
            kind = e.get("type")
            if kind == "wifi":
                e.setdefault("icon_size", 24)
            if kind in {"label", "conn", "page_button", "toggle", "sensor", "status"}:
                e.setdefault("font", "montserrat")
            if kind in {"toggle", "status"}:
                e.setdefault("off_opacity", 100)
            if kind in {"page_button", "toggle", "sensor", "status"}:
                for key, value in _SHADOW_DEFAULTS.items():
                    e.setdefault(key, value)
    return design


def validate(design):
    """Return a list of readable problems. An empty list means it's safe to generate."""
    if not isinstance(design, dict):
        return ["Design must be an object"]
    errors = []
    if design.get("display") not in DISPLAYS:
        return ["The design's display isn't one this app knows"]
    device = design.get("device")
    if not isinstance(device, dict):
        errors.append("Device settings are missing")
    else:
        name = device.get("name")
        if not (isinstance(name, str) and re.fullmatch(r"[a-z0-9-]{1,31}", name)):
            errors.append("Device name can only use a-z, 0-9 and hyphens (31 characters at most)")
        if not (_text(device.get("friendly_name")) and device["friendly_name"].strip()):
            errors.append('Friendly name needs text, without ", \\ or $')

    pages = design.get("pages")
    if not isinstance(pages, list) or not pages:
        return errors + ["The design needs at least one page"]
    page_ids, element_ids = set(), set()
    for page in pages:
        if not isinstance(page, dict) or not (isinstance(page.get("id"), str) and _SLUG.fullmatch(page["id"])):
            errors.append("A page has an invalid ID")
            continue
        if page["id"] in page_ids:
            errors.append(f"Duplicate page ID {page['id']}")
        page_ids.add(page["id"])

    for page in pages:
        if not isinstance(page, dict):
            continue
        where = page.get("name") or page.get("id")
        if not _COLOUR_RULE[0](page.get("bg")):
            errors.append(f"{where}: background {_COLOUR_RULE[1]}")
        elements = page.get("elements")
        if not isinstance(elements, list):
            errors.append(f"{where}: elements are missing")
            continue
        for e in elements:
            errors += _validate_element(e, where, page_ids, element_ids, DISPLAYS[design["display"]])
    return errors


def _validate_element(e, page_name, page_ids, element_ids, display):
    if not isinstance(e, dict) or e.get("type") not in REQUIRED:
        return [f"{page_name}: unknown element type"]
    label = f"{page_name} / {e.get('text') or e['type']}"
    errors = []
    eid = e.get("id")
    if not (isinstance(eid, str) and _SLUG.fullmatch(eid)):
        errors.append(f"{label}: invalid ID")
    elif eid in element_ids:
        errors.append(f"{label}: duplicate ID {eid}")
    else:
        element_ids.add(eid)
    required = {"x", "y", "align", *REQUIRED[e["type"]]}
    # A toggle with no icon is a plain text button, like "All Systems Normal"
    if e["type"] == "toggle" and e.get("icon") == "":
        required.discard("icon")
    for key in sorted(required):
        if key not in e:
            errors.append(f"{label}: {key} is missing")
            continue
        check, message = RULES[key]
        if not check(e[key]):
            errors.append(f"{label}: {key} {message}")
    # Elements can run past the screen edge, where the panel just cuts them off. This catches typos.
    for key, limit in (("w", display["width"]), ("x", display["width"]), ("h", display["height"]), ("y", display["height"])):
        if key in e and RULES[key][0](e[key]) and abs(e[key]) > limit * 2:
            errors.append(f"{label}: {key} is more than twice this {display['width']}x{display['height']} screen")
    if e["type"] == "page_button" and e.get("target") not in page_ids:
        errors.append(f"{label}: button points at a page that doesn't exist")
    if e["type"] == "slider" and not str(e.get("entity")).startswith("light."):
        errors.append(f"{label}: a brightness slider needs a light entity")
    return errors


def _scaled(height, offset, base):
    """Keep a tile's contents proportional when the tile is resized."""
    return math.floor(offset * height / base + 0.5)


def _c_string(value):
    # YAML single-quoted lambdas need ' doubled. validate() has already removed " and \.
    return '"' + value.replace("'", "''") + '"'


def _sensor_format(e):
    fmt = f"%.{e['decimals']}f" + e["unit"].replace("%", "%%")
    return json.dumps(fmt, ensure_ascii=False)


def _sensor_placeholder(e):
    dashes = "--." + "-" * e["decimals"] if e["decimals"] else "--"
    return json.dumps(dashes + e["unit"], ensure_ascii=False)


def _built_in(font, size):
    return font == "montserrat" and size in BUILT_IN_MONTSERRAT


def _page_button_text(e):
    # The arrows in built-in Montserrat are LVGL symbols that downloaded fonts don't have
    left, right = ("\\uF053", "\\uF054") if _built_in(e["font"], e["text_size"]) else ("\u2039", "\u203a")
    text = {"left": f"{left} {e['text']}", "right": f"{e['text']} {right}"}.get(e["chevron"], e["text"])
    return f'"{text}"'


def _font_id(e, size):
    return f"{e['font']}_{size}"


def _image_id(e):
    return f"img_{e['src'].split('.')[0]}_{e['w']}x{e['h']}"


_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(HERE),
    autoescape=False,  # output is YAML; every value is validated, and text goes through |q
    trim_blocks=True,
    lstrip_blocks=True,
    undefined=jinja2.StrictUndefined,
)
_env.filters.update(
    q=lambda v: json.dumps(v, ensure_ascii=False),
    c=lambda v: "0x" + v[1:].upper(),
    glyph=lambda name: f'"\\U{ICONS[name].zfill(8)}"',
    scaled=_scaled,
    cstr=_c_string,
    sensor_format=_sensor_format,
    sensor_placeholder=_sensor_placeholder,
    page_button_text=_page_button_text,
    fid=_font_id,
    image_id=_image_id,
)


def _fonts(elements):
    glyphs = {}

    def use(size, *names):
        glyphs.setdefault(size, set()).update(ICONS[n] for n in names if n)

    for e in elements:
        if e["type"] == "wifi":
            use(e["icon_size"], "wifi", "wifi-off")
        elif e["type"] == "status":
            use(e["icon_size"], e["on_icon"], e["off_icon"])
        elif "icon" in e:
            use(e["icon_size"], e["icon"])
    return [(size, [c.zfill(8) for c in sorted(codes)]) for size, codes in sorted(glyphs.items()) if codes]


def _custom_fonts(elements):
    """One font block per downloaded family and size, with any characters beyond basic Latin."""
    used = {}
    for e in elements:
        if "font" not in e:
            continue
        sizes = {e["text_size"], e.get("value_size", e["text_size"])}
        if e["type"] == "status":
            sizes.add(16)
        text = "".join(str(e.get(k, "")) for k in ("text", "unit", "on_text", "off_text"))
        if e["type"] == "page_button":
            text += {"left": "\u2039", "right": "\u203a"}.get(e["chevron"], "")
        for size in sizes:
            if not _built_in(e["font"], size):
                used.setdefault((e["font"], size), set()).update(c for c in text if ord(c) > 0x7E)
    return [{"id": f"{font}_{size}", "family": FONTS[font][0], "weight": FONTS[font][1], "size": size,
             "glyphs": sorted(glyphs)} for (font, size), glyphs in sorted(used.items())]


def _images(elements, base_url):
    """One image per file and size. ESPHome downloads each one from this app when it compiles."""
    return {_image_id(e): {"url": f"{base_url.rstrip('/')}/images/{e['src']}", "w": e["w"], "h": e["h"],
                           "alpha": e["src"].endswith(".png")}
            for e in elements if e["type"] == "image"}


def generate(design, base_url=""):
    """Render the YAML. Call validate() first; this assumes the design is clean."""
    elements = [e for page in design["pages"] for e in page["elements"]]
    of_type = lambda t: [e for e in elements if e["type"] == t]  # noqa: E731
    yaml = _env.get_template("panel.yaml.j2").render(
        display=design["display"],
        display_label=DISPLAYS[design["display"]]["label"],
        custom_fonts=_custom_fonts(elements),
        device=design["device"],
        pages=design["pages"],
        theme=THEME,
        fonts=_fonts(elements),
        state_toggles=[e for e in of_type("toggle") if e["show_state"]],
        statuses=of_type("status"),
        sensors=of_type("sensor"),
        sliders=of_type("slider"),
        images=_images(elements, base_url),
        wifis=of_type("wifi"),
        conns=of_type("conn"),
    )
    # The macros leave stray blank lines, so drop them all and space out the top-level sections.
    out = []
    for line in filter(str.strip, yaml.splitlines()):
        if not line.startswith(" ") and out and not out[-1].startswith("#"):
            out.append("")
        out.append(line)
    return "\n".join(out) + "\n"
