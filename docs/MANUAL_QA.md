# Manual QA checklist

- Start on a clean Windows account with no `.env` and no AI key.
- Open the dashboard, add a manual job, search/filter it, inspect the source detail, and edit its status/notes.
- Confirm opening a source link does not change status; only a deliberate status update marks Applied.
- Update profile skills and verify the deterministic score and reasons change.
- Run a scan against each enabled public feed; confirm errors are visible and successful cards retain source credit/link.
- Import a CSV, inspect preview, confirm import, then export CSV and open it in a spreadsheet.
- Upload a PDF and DOCX under 5 MB; confirm extracted text is editable. Try an unsupported type and oversized upload.
- Save/edit a per-job draft and verify it remains local.
- Download a JSON backup and verify it contains jobs/profile/drafts; copy `instance/` with the app stopped.
- Check desktop and narrow mobile widths, keyboard focus, and form validation.
