import os
from pathlib import Path
from datetime import timedelta

from dotenv import load_dotenv
from flask import Flask, flash, redirect, request, session, url_for
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import check_password_hash

from .db import init_db

csrf = CSRFProtect()


def create_app(test_config=None):
    load_dotenv()
    app = Flask(__name__, instance_relative_config=True)
    is_vercel = bool(os.getenv("VERCEL"))
    database_url = os.getenv("DATABASE_URL")
    local_instance = Path(app.instance_path)
    if not is_vercel:
        local_instance.mkdir(parents=True, exist_ok=True)
    secret_path = local_instance / ".secret_key"
    secret_key = os.getenv("FLASK_SECRET_KEY")
    if (is_vercel or database_url) and (not database_url or not secret_key or not os.getenv("OWNER_PASSWORD_HASH")):
        missing = [name for name, value in (("DATABASE_URL", database_url), ("FLASK_SECRET_KEY", secret_key), ("OWNER_PASSWORD_HASH", os.getenv("OWNER_PASSWORD_HASH"))) if not value]
        raise RuntimeError("Hosted deployment is not configured. Set: " + ", ".join(missing))
    if not secret_key:
        if not secret_path.exists():
            secret_path.write_text(os.urandom(32).hex(), encoding="utf-8")
        secret_key = secret_path.read_text(encoding="utf-8").strip()
    app.config.update(
        SECRET_KEY=secret_key,
        DATABASE=database_url or os.getenv("DATABASE_PATH", str(local_instance / "job_hunter.sqlite3")),
        MAX_CONTENT_LENGTH=5 * 1024 * 1024,
        UPLOAD_FOLDER=str(local_instance / "uploads"),
        AUTH_REQUIRED=is_vercel or bool(database_url),
        OWNER_PASSWORD_HASH=os.getenv("OWNER_PASSWORD_HASH", ""),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=is_vercel,
        PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
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
        if app.config["SESSION_COOKIE_SECURE"]:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
        return response

    @app.before_request
    def owner_authentication():
        if not app.config["AUTH_REQUIRED"] or request.endpoint in ("main.login", "main.logout", "static"):
            return None
        if session.get("owner_authenticated"):
            return None
        if request.method in ("GET", "HEAD"):
            return redirect(url_for("main.login", next=request.full_path.rstrip("?")))
        flash("Sign in to use your private job workspace.", "error")
        return redirect(url_for("main.login"))

    app.config["PASSWORD_CHECK"] = check_password_hash

    return app
