# Vercel-hosted AI Job Hunter plan

## Overview

Move the existing Flask operations dashboard to the existing Vercel project with durable hosted storage and a private owner login. Preserve the local Windows/SQLite mode. Keep the local database and resume files on this computer unless the owner separately requests a migration.

## Architecture decisions

- Keep Flask and its current templates as the deployed application; Vercel's Python runtime supports Flask.
- Keep SQLite for local runs and add PostgreSQL for Vercel through a Marketplace connection (Neon or another PostgreSQL-compatible provider). Vercel does not provide its former built-in Postgres product for new projects.
- Require an environment-configured owner password hash and secret key in production; fail closed if required settings are missing.
- Store resume binaries and CSV import previews in the durable database for this single-owner application, avoiding a separately provisioned file service.
- Do not import the local instance database or resume files into the cloud.
- Bound source scans to a Vercel function duration and retain the app's explicit-on-demand scanning behavior.

## Ordered tasks

1. Add a dual SQLite/PostgreSQL database layer, portable schema initialization, and runtime dependencies.
2. Add owner login/session enforcement, production configuration validation, secure cookies/headers, and auth tests.
3. Move resume and CSV preview persistence onto the database; update hosted/local copy and privacy text.
4. Configure the repository root for Vercel Flask auto-detection and add deployment environment documentation.
5. Run the complete test suite, build/deployment checks, and verify the production hostname. Do not expose local personal data.

## Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| No durable PostgreSQL binding yet | Production app cannot persist safely | Deploy only after provider connection and required secrets exist; fail closed otherwise |
| Existing code contains SQLite-specific SQL | Runtime errors on PostgreSQL | Exercise portability tests and audit every SQLite-only query/exception |
| Resume/profile data is sensitive | Public disclosure risk | Owner-only auth, secure session cookie, CSRF, private DB, no local data migration |
| Scans make external calls in one request | Function timeouts/provider availability | Keep explicit scans, provider timeouts, and rely on the configured function duration limit |

## Completion criteria

- Local SQLite tests and workflows continue to work.
- Unauthenticated hosted requests cannot access dashboard, resume/profile, job data, drafts, imports, exports, or scans.
- PostgreSQL schema and CRUD work against a real provider connection before production is switched.
- Vercel production serves the real dashboard and passes an authenticated smoke check.
- Local personal data remains local.
