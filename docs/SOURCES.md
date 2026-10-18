# Job sources

## Remotive

- API: [Remote Jobs API](https://github.com/remotive-com/remote-jobs-api), endpoint `GET https://remotive.com/api/remote-jobs`.
- No API key. The adapter passes `search` and `limit`, parses the `jobs` array and strips description HTML to text.
- The API has no country filter. The International scan uses conservative matching against the source's stated candidate eligibility. Remotive is not used for India scans.
- The provider says data is delayed 24 hours, recommends at most four calls/day, and requires a link to each Remotive listing plus Remotive source credit. It disallows resubmission to third-party job aggregators.

## Himalayas

- API: [Remote Jobs API docs](https://himalayas.app/docs/remote-jobs-api), endpoint `GET https://himalayas.app/jobs/api/search`.
- No API key. The adapter passes a query and recent sort, parses the `jobs` array, and retains `applicationLink`/`guid`.
- The adapter passes `country=India` for India searches and the selected country for international searches. This source is remote-focused.
- Provider documentation states the feed refreshes every 24 hours, recommends caching, requires source credit and listing links, and disallows resubmission to third-party aggregators.

## Greenhouse and Lever company boards

- Greenhouse uses the public Job Board API: [official documentation](https://docs.greenhouse.io/job-board). Add up to 10 board tokens in Settings. A token is company-specific; the adapter cannot search every Greenhouse employer.
- Lever uses the public postings endpoint documented by [Lever's official postings API repository](https://github.com/lever/postings-api). Add up to 10 site names in Settings. A site name is company-specific; the adapter cannot search every Lever employer.
- These adapters use public GET endpoints, match the search phrase against job content, then conservatively classify India vs selected international country using returned location fields. They mark eligibility and work mode as unknown when the board does not state it.

Sources do not represent all jobs and can change or be unavailable. The app retries a connection or timeout once; scan history records a concise failure category. An explicit scan can make up to two requests when the first fails before producing a response. All listings retain attribution and source links where provided. Manual entry and CSV import are available. The app does not scrape access-controlled boards.
