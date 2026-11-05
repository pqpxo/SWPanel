"""SWPanel: a drag-and-drop designer that outputs ESPHome LVGL YAML."""
import hashlib
import json
import os
import socket
import urllib.request
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request, send_from_directory
from sqlalchemy import Integer, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from werkzeug.middleware.proxy_fix import ProxyFix

import yamlgen

HERE = Path(__file__).parent
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self'; "
       "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors ")
INGRESS_PEER = "172.30.32.2"  # Home Assistant's Ingress proxy, the only address allowed to use the app
STARTERS = {"waveshare_35": "default_design.json", "crowpanel_7": "default_crowpanel_7.json"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024
# Content type: (how the file starts, extension). SVG stays out, as it can carry scripts.
IMAGE_TYPES = {"image/png": (b"\x89PNG\r\n\x1a\n", "png"), "image/jpeg": (b"\xff\xd8\xff", "jpg")}


class Base(DeclarativeBase):
    pass


class Design(Base):
    __tablename__ = "design"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    data: Mapped[str] = mapped_column(Text)


def _starter(display):
    return (HERE / STARTERS[display]).read_text(encoding="utf-8")


def create_app(data_dir=None):
    data_dir = Path(data_dir or os.environ.get("DATA_DIR", HERE / "data"))
    images_dir = data_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{data_dir / 'swpanel.db'}")
    Base.metadata.create_all(engine)

    app = Flask(__name__)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024

    # The Supervisor sets this token, so it marks the app as running inside Home Assistant
    addon = bool(os.environ.get("SUPERVISOR_TOKEN"))
    csp = CSP + ("'self'" if addon else "'none'")  # Ingress shows the app in a same-origin iframe
    addon_url = ""
    if addon:
        options = data_dir / "options.json"
        addon_url = (json.loads(options.read_text(encoding="utf-8")) if options.exists() else {}).get("public_url")
        addon_url = addon_url or f"http://{socket.gethostname()}:{os.environ.get('PORT', '8095')}"

        @app.before_request
        def ingress_only():
            # ProxyFix rewrites remote_addr from request headers, which a client can fake
            peer = request.environ["werkzeug.proxy_fix.orig"]["REMOTE_ADDR"]
            # ESPHome has no login to offer when it downloads images at compile time
            if peer != INGRESS_PEER and request.endpoint not in ("healthz", "image"):
                abort(403)

    with Session(engine) as session:
        if session.scalar(select(Design.id).limit(1)) is None:
            session.add(Design(data=_starter("waveshare_35")))
            session.commit()

    @app.after_request
    def security_headers(response):
        response.headers["Content-Security-Policy"] = csp
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/healthz")
    def healthz():
        return jsonify(status="ok")

    @app.get("/api/displays")
    def displays():
        return jsonify(yamlgen.DISPLAYS)

    @app.get("/api/designs")
    def list_designs():
        with Session(engine) as session:
            rows = session.scalars(select(Design).order_by(Design.id)).all()
            designs = [(row.id, yamlgen.upgrade(json.loads(row.data))) for row in rows]
        return jsonify([{"id": design_id, "name": design["device"]["friendly_name"], "display": design["display"]}
                        for design_id, design in designs])

    @app.post("/api/designs")
    def create_design():
        body = request.get_json()
        display = body.get("display") if isinstance(body, dict) else None
        if display not in STARTERS:
            return jsonify(errors=["Unknown display"]), 400
        with Session(engine) as session:
            row = Design(data=_starter(display))
            session.add(row)
            session.commit()
            return jsonify(id=row.id), 201

    @app.get("/api/designs/<int:design_id>")
    def get_design(design_id):
        with Session(engine) as session:
            row = session.get(Design, design_id) or abort(404)
            return jsonify(yamlgen.upgrade(json.loads(row.data)))

    @app.put("/api/designs/<int:design_id>")
    def save_design(design_id):
        # Saved as you type, so half-finished values are fine here.
        # The strict check runs when YAML is requested.
        design = request.get_json()
        if not isinstance(design, dict) or not isinstance(design.get("pages"), list):
            return jsonify(errors=["Not a panel design"]), 400
        with Session(engine) as session:
            row = session.get(Design, design_id) or abort(404)
            row.data = json.dumps(design, ensure_ascii=False)
            session.commit()
        return jsonify(status="saved")

    @app.delete("/api/designs/<int:design_id>")
    def delete_design(design_id):
        with Session(engine) as session:
            row = session.get(Design, design_id) or abort(404)
            if len(session.scalars(select(Design.id)).all()) < 2:
                return jsonify(errors=["Can't delete the only design"]), 400
            session.delete(row)
            session.commit()
        return jsonify(status="deleted")

    @app.get("/api/ha/entities")
    def ha_entities():
        # Goes through the server so the token never reaches the browser
        if addon:
            url, token = "http://supervisor/core", os.environ["SUPERVISOR_TOKEN"]
        else:
            url, token = os.environ.get("HA_URL", "").rstrip("/"), os.environ.get("HA_TOKEN", "")
        if not (url and token):
            return jsonify(configured=False, entities=[])
        call = urllib.request.Request(f"{url}/api/states", headers={"Authorization": f"Bearer {token}"})
        try:
            with urllib.request.urlopen(call, timeout=5) as response:
                entities = [{"id": s["entity_id"], "name": s.get("attributes", {}).get("friendly_name", ""),
                             "state": s.get("state", ""), "brightness": s.get("attributes", {}).get("brightness")}
                            for s in json.load(response)]
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            return jsonify(configured=True, entities=[]), 502
        return jsonify(configured=True, entities=sorted(entities, key=lambda e: e["id"]))

    @app.post("/api/images")
    def upload_image():
        # A raw body with an image content type can't be sent cross-site without a preflight, which fails here
        kind = IMAGE_TYPES.get(request.mimetype)
        if not kind:
            return jsonify(errors=["Use a PNG or JPEG image"]), 415
        request.max_content_length = MAX_IMAGE_BYTES
        data = request.get_data()
        if not data.startswith(kind[0]):
            return jsonify(errors=["That file isn't a valid PNG or JPEG image"]), 400
        name = f"{hashlib.sha256(data).hexdigest()[:16]}.{kind[1]}"
        (images_dir / name).write_bytes(data)
        return jsonify(src=name), 201

    @app.get("/images/<name>")
    def image(name):
        return send_from_directory(images_dir, name)

    @app.post("/api/yaml")
    def get_yaml():
        design = yamlgen.upgrade(request.get_json())
        errors = yamlgen.validate(design)
        if errors:
            return jsonify(errors=errors), 400
        return jsonify(yaml=yamlgen.generate(design, os.environ.get("PUBLIC_URL") or addon_url or request.url_root))

    return app


app = create_app()
