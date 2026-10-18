# AI Job Hunter

A local-first job search workspace for discovering roles, checking an explainable fit estimate, and managing application preparation. It uses Flask and SQLite; no account, paid service, Docker, Node, or AI key is required. All applications remain a manual action by you.

## Windows setup

1. Install Python 3.10 or newer.
2. Double-click `scripts/setup_windows.bat` once.
3. Start the app with `scripts/run_windows.bat`.
4. Visit [http://127.0.0.1:5000](http://127.0.0.1:5000). Keep the terminal open; Ctrl+C stops the app.

Manual setup: `py -3 -m venv .venv`, `.venv\Scripts\activate`, `python -m pip install -r requirements.txt`, then `python app.py`.

## Daily workflow

- Use **Discover → India Jobs** or **International Jobs**. India is the default; International requires a country/region. Himalayas receives the selected country filter. Remotive is international-only because it has no reliable country filter. Each scan happens only after you press Start scan.
- Greenhouse and Lever are optional company-board sources. Enable them in Settings and add the public board token/site name for each company you want searched. These sources do not search the entire market.
- Add a role manually or use CSV import. The CSV import previews rows and skips duplicate URLs.
- Review the listing and its original source, update status and notes, and create editable per-job drafts. Mark Applied only after you submit externally.
- Edit target titles, locations, and confirmed skills under Profile. Scores are deterministic prioritization aids, not eligibility or hiring predictions.

Remote listings can have country restrictions. The app keeps source eligibility text and does not infer India eligibility from the word “remote.” Remotive and Himalayas require source attribution and links; this app displays both. International country preferences are optional and editable under Profile. Visa, sponsorship, and relocation show “Not specified” unless a source or you provide that information.

Choose **Use light theme** or **Use dark theme** in the header. On first visit, the app follows the operating-system preference; a choice is saved in this browser.

## Local data and backups

The SQLite database and uploaded resumes live under `instance/` (or the path in `DATABASE_PATH`). Resume uploads are limited to 5 MB and PDF/DOCX extraction runs locally. The original file is preserved. To back up everything, stop the app and copy the whole `instance/` directory to a private location. **Settings → Download JSON backup** includes job, profile, and draft data; CSV is for job rows. Keep backups private.

`.env` is optional and ignored by Git. Copy `.env.example` if you want to set a local Flask secret. No AI integration is active in this initial build; no resume or profile data is sent to an AI provider. Do not put secrets in source control.

## Tests

With the environment active, run `python -m pytest`. Tests use temporary databases and mocked provider responses. They do not contact job APIs.

## Troubleshooting

- **Python not found:** install Python 3.10+ and enable the Python launcher, then rerun setup.
- **Port 5000 in use:** stop the other local Flask process and retry.
- **Source scan error:** connection/timeout failures get one retry. If the provider is still unavailable, scan history names the failure category; retry later or use manual entry/CSV. A successful scan can add zero jobs when all returned listings were already saved.
- **Resume text is blank:** image-only/scanned PDFs may not contain extractable text; paste the text manually. The upload stays saved.
- **Lost/changed data:** restore the stopped-app `instance/` backup. Avoid opening the same SQLite database from multiple app copies.

## Hosting

This release is intended for one computer and binds only to `127.0.0.1`. Do not expose it to the public internet: it has no user authentication. Local SQLite and uploaded files are not reliable persistent storage for Vercel serverless functions. A future hosted version needs authentication, CSRF/session hardening, durable shared storage such as managed Postgres/object storage, and a separately managed discovery worker. The local app runs only while the computer is on.

The Vercel project in `vercel-site/` is an informational landing page only. It does not host the Flask dashboard or any personal job, profile, or resume data.
