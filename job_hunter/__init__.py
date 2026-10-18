import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask
from flask_wtf.csrf import CSRFProtect

from .db import init_db

csrf = CSRFProtect()


def create_app(test_config=None):
    load_dotenv()
    app = Flask(__name__, instance_relative_config=True)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    secret_path = Path(app.instance_path) / ".secret_key"
    secret_key = os.getenv("FLASK_SECRET_KEY")
    if not secret_key:
        if not secret_path.exists():
            secret_path.write_text(os.urandom(32).hex(), encoding="utf-8")
        secret_key = secret_path.read_text(encoding="utf-8").strip()
    app.config.update(
        SECRET_KEY=secret_key,
        DATABASE=os.getenv("DATABASE_PATH", str(Path(app.instance_path) / "job_hunter.sqlite3")),
        MAX_CONTENT_LENGTH=5 * 1024 * 1024,
        UPLOAD_FOLDER=str(Path(app.instance_path) / "uploads"),
        WTF_CSRF_TIME_LIMIT=None,
    )
    if test_config:
        app.config.update(test_config)
    csrf.init_app(app)
    init_db(app.config["DATABASE"])

    from .routes import bp
    app.register_blueprint(bp)

    @app.after_request
    def secure_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; base-uri 'self'; form-action 'self'")
        return response

    return app
