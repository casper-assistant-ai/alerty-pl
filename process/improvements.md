# Improvements backlog

The issue-worker takes the first open item when no issue, dev-task or refused agent PR waits,
at most one improvement PR a day, and ticks the item (`- [x] … (#PR)`) in that PR. The
process-retro adds items here when the list runs short. Every item is product work: tests,
reliability or simpler upkeep, never a report.

## Tests
- [ ] `scripts/changelog.py`: tests for `lint` (good and bad subjects, `!` and `BREAKING CHANGE:`) and for the next version number.
- [ ] `docs/common.js`: a node test (no npm) for the date and category helpers used by every page.
- [ ] `scripts/rcb.py update`: a test that a page that fails to load keeps the old `archive.json` entries.

## Reliability
- [ ] `scripts/rcb.py`: retry a gov.pl request once on a timeout or a 5xx before failing the run, with a test.
- [ ] `scripts/site_check.mjs`: report the page and the first failing request in one line, so the site-fixer gets a clear cause.
- [ ] `scripts/retro.py`: handle an HTTP 403/429 from the GitHub API with one retry and a clear error.

## Simpler upkeep
- [ ] `docs/*.js`: move helpers that two pages copy into `common.js`.
- [ ] `scripts/rcb.py`: split the longest function into named steps, with no change in output (tests stay green).
