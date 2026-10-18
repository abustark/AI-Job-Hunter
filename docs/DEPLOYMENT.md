# Deployment

The supported deployment is local Windows. Run `scripts/setup_windows.bat`, then `scripts/run_windows.bat`. Flask binds to `127.0.0.1:5000` and the app stores state in SQLite under `instance/`.

This is not a public production deployment. There is no login, and a serverless Vercel filesystem is not a durable SQLite or upload store. Future hosting requires authentication, a managed database and file store, secure production cookie/session settings, CSRF protection, and a worker for scheduled source refresh. Keep the local scanner independent from request handlers if it becomes a hosted service. Do not claim scans continue while the local PC is off.

## Vercel project page

`vercel-site/` is a static, informational page for the project. Deploy it with that directory as the Vercel project root. It contains no Flask routes, personal data, or job-search forms; deploying it does not host the local app. The local dashboard remains private on the owner's computer until authentication and durable hosted storage are implemented.
