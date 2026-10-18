# Security and privacy

- Server binds to loopback `127.0.0.1`; no authentication is provided, so do not expose the server publicly.
- State-changing forms use Flask-WTF CSRF tokens. SQLite uses parameterized SQL, foreign keys, and local-only storage.
- Database, uploads, `.env`, backups, logs and exports are excluded by `.gitignore`. Uploads are limited to 5 MB and accepted only as PDF/DOCX; filenames are sanitized; files are not executed.
- PDF/DOCX extraction runs locally. External source APIs receive search phrases when a user starts a scan. There is no active AI call in this release.
- Descriptions are rendered as escaped plain text. Source content is untrusted data.
- CSV export prefixes formula-leading values. Keep downloaded backups private because JSON contains profile and draft data.
- Stop the app before copying/restoring `instance/`. Do not share the local database or resume folder unintentionally.
