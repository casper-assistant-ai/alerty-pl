# Process retro log

One row a day from the process-retro agent (weekly until 2026-11-21, daily since 2026-11-22):
the development share of agent output over the rolling last 7 days (product PRs merged / all
agent output) and what it changed. Newest last.

| date | dev share (7 days) | product PRs | docs/chore + reports | change |
|---|---|---|---|---|
| 2026-11-14 | 60% | 3 | 2 | first retro (workflows live 11-21): dev-task status tests + dev-task site links, docs-keeper extra sun run (weekly slot missed go-live) |
| 2026-11-21 | 60% | 3 | 2 | second run of the day, window unchanged: site-designer extra sun run — dev-task #10 is due before the 11-23 retro but its own slot is wed 11-25; no other change (morning's changes need days to show) |
| 2026-11-22 | 70% | 7 | 3 | block refreshed (70%; the 5 no-product days are pre-live, window to 11-29 is all live: no day without a merge); dev-task map legend category filter → site-designer |
| 2026-11-23 | 69% | 11 | 5 | dev-task history period `?od=&do=` → site-designer (the 11-22 one landed, PR #29); block numbers refreshed; no schedule/improvements change: both sun extra runs bore merges on their first Sunday, backlog has 6 open items |
| 2026-11-24 | 64% | 18 | 10 | block refreshed (64%; 11-24 no merge by the retro: gov.pl unreachable from the runners 22:57–06:25 UTC closed #74 and #76 unjudged, z.ai 529 killed every agent run 01:39–09:51) and a hold-while-Update-data-is-red duty added; dev-task fires from GIBS WMTS + failure note → site-designer (the 11-23 one landed, PR #71); no schedule change, backlog has 10 open items. Gave up: #73 lesson |
| 2026-11-25 | 66% | 21 | 11 | block refreshed (66%; every live day 11-21..11-25 merged, but 11-24 was the #94/#106 repair pair and 11-25 a script fix: no dev-task was open after #94 closed); dev-tasks opened and handed to the issue-worker at once: parser, one record per alert in `alerts.json` (the duplicate daily-status #122 found) → parser-doctor, and the PL/EN/UK base, slice 1 of #58 → site-designer; no schedule change (both Sunday runs merged on their first Sunday, the second is 11-29); backlog: slice 1's dictionaries moved to `docs/i18n.js` (the gate allows no new folder) and browser-language detection to the last slice (the Site check's Chrome is `en-US`); the #73 lesson corrected after #106 (the WMTS retry served no tile live) |
| 2026-11-26 | 54% | 32 | 27 | no change: every live day merged (6 of 6), share still above the 50% target; parser-doctor and security-fixer idle with no work found, ci-doctor and daily-status are reporters by design; the 11-25 parser and PL/EN/UK dev-tasks are still the open work, no new one; no schedule/improvements change, the block numbers stay (56% → 54% is noise) |
