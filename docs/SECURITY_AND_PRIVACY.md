# Security and privacy

- Local mode binds to loopback `127.0.0.1` and uses SQLite. Hosted mode requires PostgreSQL plus `FLASK_SECRET_KEY` and `OWNER_PASSWORD_HASH`; it rejects requests until those settings exist.
- Hosted routes require the owner session. State-changing forms use Flask-WTF CSRF tokens; the hosted session cookie is secure, HTTP-only, same-site, and expires after 12 hours. Failed logins are throttled.
- SQL uses parameters and foreign keys. Resume originals and import previews use the configured database in both modes; hosted downloads go through the authenticated Flask app.
- Local database, `.env`, backups, logs and exports are excluded by `.gitignore`. Uploads are limited to 5 MB and accepted only as PDF/DOCX; filenames are sanitized; files are not executed.
- PDF/DOCX extraction runs in the app's Python process (on the owner's computer in local mode). External source APIs receive search phrases when a user starts a scan. There is no active AI call in this release.
- Descriptions are rendered as escaped plain text. Source content is untrusted data.
- CSV export prefixes formula-leading values. Keep downloaded backups private because JSON contains profile and draft data.
- Keep cloud database credentials private and do not deploy previews against production data. The local database and resumes are not migrated automatically. Keep downloaded backups private because they contain profile and draft data.
