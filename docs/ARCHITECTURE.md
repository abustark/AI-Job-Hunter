# Architecture

## Capability map

| Module | Responsibility | Depends on |
|---|---|---|
| web | Flask routes, server-rendered templates, CSRF | database, matching, sources |
| database | SQLite/PostgreSQL schema, connections, records | — |
| matching | Deterministic fit estimate and explanations | profile/job records |
| sources | HTTP source adapters and normalization | requests |
| documents | Local PDF/DOCX text extraction and drafts | profile/job records |

Build order: database → matching and sources → web workflows → documents.

Tables: jobs, profile, scan_runs, drafts, events, resume_files, import_previews, and login_attempts. Timestamps are ISO UTC. Jobs use a unique `(source, source_id)` key when a provider supplies an ID; original URLs provide a secondary duplicate check. SQL access is parameterized. Provider calls have a 15-second timeout and run only from an explicit scan POST.

The source adapter boundary is `job_hunter/sources.py`: adapters return normalized dictionaries. The matching function is independent of Flask. Local mode uses SQLite; Vercel mode uses the configured PostgreSQL database because serverless files are not durable.
