# Deployment

## Local Windows

Run `scripts/setup_windows.bat`, then `scripts/run_windows.bat`. Flask binds to `127.0.0.1:5000` and stores its SQLite database and resume originals under `instance/`. The local app runs only while the computer is on.

## Vercel dashboard

The repository root is the Vercel project root. Vercel detects the Flask WSGI application exported as `app` from `app.py` and runs it on the Python runtime. Scans remain user-triggered and make external provider calls during that request; they are not scheduled and do not run while the app is idle. Provider requests have 15-second timeouts; Vercel applies its configured function-duration limit to the full scan request.

### Required services and environment

The existing Vercel project currently needs a PostgreSQL-compatible database connected before it can serve the dashboard. Vercel Marketplace integrations can provision providers such as Neon or Supabase and inject credentials. Provider plans and billing are controlled by the provider/account; review those terms before provisioning. Use a private database with TLS enabled and restrict its credentials to this project.

Add these values to the Vercel project for the Production environment:

| Name | Value |
|---|---|
| `DATABASE_URL` | PostgreSQL connection URL supplied by the provider; include its required TLS parameters |
| `FLASK_SECRET_KEY` | A new random secret, generated for this app and stored only as an encrypted Vercel environment variable |
| `OWNER_PASSWORD_HASH` | A Werkzeug password hash generated locally with `scripts/make_owner_hash.py`; do not use or upload the plaintext password |

The app fails closed at startup when any of those settings is missing in Vercel. It uses an owner-only sign-in, CSRF protection, HTTP-only same-site secure cookies, a 12-hour session, login attempt throttling, and security headers. Do not add these secrets to GitHub or a `.env` file committed to the repository. Avoid sharing the production database with preview deployments; use a separate preview database if previews are enabled.

To generate values locally:

1. Create a private PostgreSQL database using the Vercel Marketplace or a provider you already use. Connect it to this Vercel project and map the provider's connection URL into `DATABASE_URL`.
2. Run `.venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"` and add the output as `FLASK_SECRET_KEY` in Vercel.
3. Run `.venv\Scripts\python.exe scripts\make_owner_hash.py` and add the printed hash as `OWNER_PASSWORD_HASH`. Keep the password you typed in your password manager.
4. Deploy from the repository root with `vercel --prod` after all three variables are present. The first database connection creates/updates the schema.

### Data migration and operations

The hosted database starts empty. The local SQLite DB, profile, job pipeline, and resume files are intentionally not copied. If you want to migrate records, sign in after deployment and use the app's import workflow/backup deliberately; handle resume originals separately and securely. Confirm a backup before any migration.

The hosted app supports manual entry, CSV import/export, job search, pipeline/status updates, profile/resume management, database-backed resume storage, source scans, and JSON backup. It does not run background scans. Provider outages, Vercel limits, or database connectivity issues can interrupt an on-demand scan; the scan history records its result.

### Current project status

The project `ai-job-hunter-site` is linked at the repository root, but it currently has no environment variables or managed database attached. Its existing production deployment is still the previous informational page. Do not switch the production alias until the database and three secrets above have been installed and the authenticated hosted workflow has been verified.
