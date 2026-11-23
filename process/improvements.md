# Improvements backlog

The issue-worker takes the first open item when no issue or dev-task waits,
at most one improvement PR a day, and ticks the item (`- [x] … (#PR)`) in that PR. The
process-retro adds items here when the list runs short. Every item is product work: tests,
reliability or simpler upkeep, never a report.

## Tests
- [x] `scripts/changelog.py`: tests for `lint` (good and bad subjects, `!` and `BREAKING CHANGE:`) and for the next version number. — this PR
- [x] `docs/common.js`: a node test (no npm) for the date and category helpers used by every page. (#20)
- [x] `scripts/rcb.py update`: a test that a page that fails to load keeps the old `archive.json` entries. — this PR
- [x] `scripts/changelog.py`: every `LEGACY` hand-mapping parses as a Conventional Commit, and the prose commit 8253358 reads through it as `ci` with no release (#55, #57). — this PR

## Reliability
- [ ] `scripts/rcb.py`: retry a gov.pl request once on a timeout or a 5xx before failing the run, with a test.
- [ ] `scripts/site_check.mjs`: report the page and the first failing request in one line, so the site-fixer gets a clear cause.
- [x] `scripts/site_check.mjs`: count the live notification service's failed requests apart from the tile servers, so an outage of `server/` reads as one line per run and no longer tips the NASA view over the limit (#70). — this PR
- [ ] `scripts/retro.py`: handle an HTTP 403/429 from the GitHub API with one retry and a clear error.

## Simpler upkeep
- [ ] `docs/*.js`: move helpers that two pages copy into `common.js`.
- [ ] `scripts/rcb.py`: split the longest function into named steps, with no change in output (tests stay green).

## Site languages PL/EN/UK (#58)
The whole interface is Polish today (`lang="pl"`, Polish strings in every page and script —
about 300 keys over `docs/*.html` and `docs/*.js`). Built as ordered feature slices below, one PR
each; from the first slice on, a test keeps `docs/i18n/pl.json`, `en.json` and `uk.json` on the
same keys. Alert texts from RCB (and the hand-kept `docs/events/incursions.json` narratives) stay
as published, behind a UI label such as «Original RCB message (Polish)». Builder: site-designer
(named so the retro can turn these into dev-tasks). The notification texts of the issue's scope
live in `server/`, which agents do not change (AGENTS.md) — recorded here only as the boundary of
this plan, not as an item.
- [ ] i18n base: `docs/i18n/{pl,en,uk}.json` and a loader with `t(key, params)` in `docs/common.js`; the language comes from `?lang=`, then localStorage, then `navigator.languages`, falling back to `pl`; a PL/EN/UK switcher in the shared header of every page, visible at 360 px; `<html lang>` and `<title>` follow it. Translates the shared chrome only: tabs, strip, toasts, footer, page titles.
- [ ] language-aware formatting in `docs/common.js`: `plural()` with English (2 forms) and Ukrainian (3 forms, its own rules) next to the Polish one, `Intl` date and number formats per language, voivodeship names and the «woj./pow./gm.» prefixes of `regionText()`.
- [ ] map page: the UI strings of `docs/index.html` and `docs/app.js` (presets, legend, tooltips, panel rows, base-layer notes, empty states), with the RCB rows showing the original-message label.
- [ ] history and analytics pages: `docs/historia.html` + `history.js`, `docs/analityka.html` + `analytics.js`.
- [ ] shelters and notifications pages: `docs/schrony.html` + `shelters.js`, `docs/powiadomienia.html` + `notify.js`.
- [ ] the rest and the gates: `docs/zmiany.html` + `changelog.js`, the README's language note, and `scripts/site_check.mjs` + `scripts/mobile_audit.mjs` opening every page in all three languages.

## Lessons from given-up issues
The process-retro writes one line here for each issue the issue-worker gave up on (label `agent-gave-up`)
that it did not split into smaller issues: what failed and what the next attempt does instead. The
issue-worker reads this before it works any issue. At most 10 lines, newest first.
- (none yet)
