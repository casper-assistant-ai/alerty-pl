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
- [x] `scripts/agent_failures.py`: give the process-doctor the evidence it could not get on 2026-11-24 (take this first: without it every failed run reads `unknown`). — this PR (a) `gh api …/jobs/<id>/logs` refused 39 of 41 logs («the response contains terminal escape sequences; pass --allow-escape-sequences»): pass that flag, retry without it when the gh is too old for it, and strip every escape and control sequence from the lines kept. (b) A CLI step that fails at the step limit has conclusion `failure`, not `timed_out`, and the job runs on: name it `timeout` when the step lasted at least 95% of the workflow's `timeout-minutes` (site-fixer 45248741714 stopped after 25m12s of 25). (c) A run whose agent job failed only in the ignored parser step still counts as failed through the conclusion job's `Handle agent failure`: drop that mirror when the agent job has no other failed step (parser-doctor 45288784687, 45296603145; issue-worker 45287331942, still counted on 2026-11-24 after fccf91c). Tests in `tests/test_agent_failures.py` for each; check with `python3 -I -m unittest tests.test_agent_failures`, then a live `python3 -I scripts/agent_failures.py --days 1` whose runs show signal lines and no «log not read».
- [x] `scripts/rcb.py`: retry a gov.pl request once on a timeout or a 5xx before failing the run, with a test. Already so: `fetch()` tries every request three times, a timeout and an `HTTPError` 5xx included (`FetchRetries` in tests/test_rcb_rules.py). — this PR
- [x] `scripts/site_check.mjs`: report the page and the first failing request in one line, so the site-fixer gets a clear cause. Already so since #70 and #94: the heading of each page view names the page and the viewport, and `judge()` its first failing request with a count per host (tests/site_check.test.mjs). — this PR
- [x] `scripts/site_check.mjs`: count the live notification service's failed requests apart from the tile servers, so an outage of `server/` reads as one line per run and no longer tips the NASA view over the limit (#70). — this PR
- [x] `scripts/retro.py`: handle an HTTP 403/429 from the GitHub API with one retry and a clear error. — this PR

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
- [ ] i18n base: the three dictionaries in `docs/i18n.js` and a loader with `t(key, params)` in `docs/common.js`; the language comes from `?lang=`, then localStorage, falling back to `pl`; a PL/EN/UK switcher in the shared header of every page, visible at 360 px; `<html lang>` and `<title>` follow it. Translates the shared chrome only: tabs, the source link, footer, page titles. Taken by the `[dev-task]` «site: PL/EN/UK base» of 2026-11-25 (the issue-worker at once, site-designer's paths); the retro ticks it here when that PR merges. Two corrections of 2026-11-25: the dictionaries are a `docs/*.js` file, not a `docs/i18n/` folder (the gate's paths allow `docs/<name>.html|js|css` and `tests/**` only); `navigator.languages` moves to the last slice, because the page bodies are still Polish while the Site check's headless Chrome reports `en-US` and matches Polish words.
- [ ] language-aware formatting in `docs/common.js`: `plural()` with English (2 forms) and Ukrainian (3 forms, its own rules) next to the Polish one, `Intl` date and number formats per language, voivodeship names and the «woj./pow./gm.» prefixes of `regionText()`; through them the strip's and toasts' own texts (`live()`, `toast()`), which need the plural forms.
- [ ] map page: the UI strings of `docs/index.html` and `docs/app.js` (presets, legend, tooltips, panel rows, base-layer notes, empty states), with the RCB rows showing the original-message label.
- [ ] history and analytics pages: `docs/historia.html` + `history.js`, `docs/analityka.html` + `analytics.js`.
- [ ] shelters and notifications pages: `docs/schrony.html` + `shelters.js`, `docs/powiadomienia.html` + `notify.js`.
- [ ] the rest and the gates: `docs/zmiany.html` + `changelog.js`, the README's language note, and `scripts/site_check.mjs` + `scripts/mobile_audit.mjs` opening every page in all three languages; last, the first-visit choice from `navigator.languages` (#58), once every page is translated and both audit scripts run in three languages.

## Lessons from given-up issues
The process-retro writes one line here for each issue the issue-worker gave up on (label `agent-gave-up`)
that it did not split into smaller issues: what failed and what the next attempt does instead. The
issue-worker reads this before it works any issue. At most 10 lines, newest first.
- #73 FIRMS fires from GIBS WMTS: PRs #74 and #76 were closed by the gate's live parse of gov.pl (the runners had no route to it, 22:57 to 06:25 UTC on 2026-11-23/24) and never judged, and a second issue-worker run opened #76 while the first had decided to hold -> while the last Update data run fails on `fetch failed`, hold the next PR and say so on the issue. The retry (#94, 2026-11-24) then shipped a WMTS tile URL nobody had fetched: the agent sandbox has no route to GIBS, and live it served no fires until #106 took WMS back (the failure note stays) -> do not move the fires to WMTS again, and ship no external URL that was not first fetched from an ordinary connection; the Site check is the first visitor.
