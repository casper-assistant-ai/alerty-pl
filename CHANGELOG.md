# Changelog

Built by `scripts/changelog.py` from [Conventional Commits](https://www.conventionalcommits.org) and the version tags; versions follow [semver](https://semver.org). Do not edit by hand.

## Unreleased

### docs

- **agents:** keep only judgment rules; list what the checks enforce ([f714254](https://github.com/casper-assistant-ai/alerty-pl/commit/f714254))
- **agents:** every correction becomes a test, a lint rule or a CodeQL query first ([2d45139](https://github.com/casper-assistant-ai/alerty-pl/commit/2d45139))

### ci

- **rules:** check the code-checkable AGENTS.md rules in CI and the gate ([6379a68](https://github.com/casper-assistant-ai/alerty-pl/commit/6379a68))
- **gate:** the PR's own code runs without the gate's write token ([847d34d](https://github.com/casper-assistant-ai/alerty-pl/commit/847d34d))
- **issue-worker:** one queue for all runs, and report links without temporary IDs ([2922803](https://github.com/casper-assistant-ai/alerty-pl/commit/2922803))
- **update:** push the data commit with its own deploy key, which the CodeQL ruleset lets through ([6ba4c74](https://github.com/casper-assistant-ai/alerty-pl/commit/6ba4c74))
- **gate:** wait for every CodeQL run on the head before trusting the check ([df9eecc](https://github.com/casper-assistant-ai/alerty-pl/commit/df9eecc))
- **codeql:** the Leaflet query is high severity, like CodeQL's own js/xss, so its alert fails the check ([f2242af](https://github.com/casper-assistant-ai/alerty-pl/commit/f2242af))
- **codeql:** advanced setup with the repository's own queries; a PR with a new alert is not merged ([f92229e](https://github.com/casper-assistant-ai/alerty-pl/commit/f92229e))
- **lint:** ruff for Python and ESLint for JavaScript in CI, the existing findings fixed ([c5ac0a9](https://github.com/casper-assistant-ai/alerty-pl/commit/c5ac0a9))
- **issue-worker:** let its PR change README.md, as allowed-files says ([f3fdfdd](https://github.com/casper-assistant-ai/alerty-pl/commit/f3fdfdd))

## 1.30.0 (2026-11-25)

### feat

- **map:** Copernicus Sentinel-2 (10 m, true colour) under the map, the clearest day of the period or the nearest clear one ([9cf0718](https://github.com/casper-assistant-ai/alerty-pl/commit/9cf0718))

### ci

- **gate:** bind dashboard/ to the PR footer and the verdict to a PR review; pr-fixer pushes only ALLOWED ([c004808](https://github.com/casper-assistant-ai/alerty-pl/commit/c004808))

### chore

- **process:** count a failed run that is being re-run (#162) ([1ed2fdc](https://github.com/casper-assistant-ai/alerty-pl/commit/1ed2fdc))

## 1.29.1 (2026-11-25)

### fix

- **map:** a found address reads «Grunwaldzka 1, Stare Miasto, Kłodzko», with its town ([3150a49](https://github.com/casper-assistant-ai/alerty-pl/commit/3150a49))

## 1.29.0 (2026-11-25)

### feat

- **map:** find a place by address, postal code or coordinates (OpenStreetMap Nominatim) ([5439492](https://github.com/casper-assistant-ai/alerty-pl/commit/5439492))

### ci

- **workflows:** agent-dispatch, daily-status, parser-doctor: out of the 529 hours and the first quota hole (#161) ([a70a0cb](https://github.com/casper-assistant-ai/alerty-pl/commit/a70a0cb))

## 1.28.1 (2026-11-25)

### fix

- **agent-retry:** re-run only the newest failed run of one queue agent ([5b3dcca](https://github.com/casper-assistant-ai/alerty-pl/commit/5b3dcca))

### ci

- **issue-worker:** reports end in the run that reads them; start the worker when new work waits ([e6be563](https://github.com/casper-assistant-ai/alerty-pl/commit/e6be563))
- **agents:** re-run agent runs that a z.ai 429 or 529 ended with nothing sent ([acdc42a](https://github.com/casper-assistant-ai/alerty-pl/commit/acdc42a))

## 1.28.0 (2026-11-25)

### feat

- **site:** skip link on every page, theme-color meta and SVG chevrons on the period control (#157) ([01ab078](https://github.com/casper-assistant-ai/alerty-pl/commit/01ab078))

## 1.27.2 (2026-11-25)

### fix

- **map:** ask again for the Wayback release list before the page fails (#156) ([e10b1b7](https://github.com/casper-assistant-ai/alerty-pl/commit/e10b1b7))

### ci

- **workflows:** site-designer: bound the reading, send by turn 40 (#154) ([0c5aaa1](https://github.com/casper-assistant-ai/alerty-pl/commit/0c5aaa1))
- **workflows:** the maintainer also runs after Agent health and the PR reviewer ([c0e467c](https://github.com/casper-assistant-ai/alerty-pl/commit/c0e467c))

### chore

- **process:** quota twice a day, 429 [1302], site-designer bound (#153) ([a37a21c](https://github.com/casper-assistant-ai/alerty-pl/commit/a37a21c))

## 1.27.1 (2026-11-25)

### fix

- **site:** build Leaflet tooltip content with h(), never a string of data (#148) ([dc7b46a](https://github.com/casper-assistant-ai/alerty-pl/commit/dc7b46a))

### ci

- **workflows:** update.yml: stage docs/data/meta.json with a data change (#149) ([65e58a9](https://github.com/casper-assistant-ai/alerty-pl/commit/65e58a9))
- **workflows:** agent-pr-gate: stop starting the reviewer and the fixer while the provider refuses them (#138) ([073bbce](https://github.com/casper-assistant-ai/alerty-pl/commit/073bbce))
- **workflows:** the maintainer makes its label idempotently ([318918c](https://github.com/casper-assistant-ai/alerty-pl/commit/318918c))
- **workflows:** the maintainer closes review PRs through the API and labels before it needs to ([5ed2835](https://github.com/casper-assistant-ai/alerty-pl/commit/5ed2835))
- **workflows:** the maintainer retries GitHub writes and takes up a review left without a result ([e3c7b86](https://github.com/casper-assistant-ai/alerty-pl/commit/e3c7b86))
- **workflows:** the maintainer lands prompts only after review and never scripts (#146) ([8e31ed8](https://github.com/casper-assistant-ai/alerty-pl/commit/8e31ed8))
- **workflows:** the maintainer starts the process-doctor after a refused patch ([5d57a2e](https://github.com/casper-assistant-ai/alerty-pl/commit/5d57a2e))
- **workflows:** the maintainer approves CI on its own review PRs ([f6ab25d](https://github.com/casper-assistant-ai/alerty-pl/commit/f6ab25d))
- **workflows:** site-designer: name the allowed files and the pinned tests, run the node suite before the  (#142) ([54e5087](https://github.com/casper-assistant-ai/alerty-pl/commit/54e5087))
- **workflows:** process-retro: timeout-minutes 25 -> 35 (#132) ([780e973](https://github.com/casper-assistant-ai/alerty-pl/commit/780e973))
- **workflows:** daily-status, parser-doctor, process-retro, process-doctor, test-improver, agent-coach, se (#131) ([263c53c](https://github.com/casper-assistant-ai/alerty-pl/commit/263c53c))
- **workflows:** security-auditor: weekly run at 12:08 UTC, outside the hours z.ai answers 529 (#119) ([ca87653](https://github.com/casper-assistant-ai/alerty-pl/commit/ca87653))
- **workflows:** region-keeper: bound the run, noop on an empty list, 30 minutes (#113) ([a704ac9](https://github.com/casper-assistant-ai/alerty-pl/commit/a704ac9))
- **workflows:** land workflow-change issues with no human (Workflow maintainer) ([98c4525](https://github.com/casper-assistant-ai/alerty-pl/commit/98c4525))

## 1.27.0 (2026-11-25)

### feat

- **site:** changes page in PL/EN/UK, first visit follows the browser's language, site check in all three languages (#58) ([7efe1ae](https://github.com/casper-assistant-ai/alerty-pl/commit/7efe1ae))
- **site:** shelters and notifications pages in PL/EN/UK (#58) ([0bc27cf](https://github.com/casper-assistant-ai/alerty-pl/commit/0bc27cf))
- **site:** history and analytics pages in PL/EN/UK (#58) ([a52984c](https://github.com/casper-assistant-ai/alerty-pl/commit/a52984c))
- **site:** map and compare pages in PL/EN/UK, RCB rows marked as the original Polish message (#58) ([23ea054](https://github.com/casper-assistant-ai/alerty-pl/commit/23ea054))

## 1.26.0 (2026-11-25)

### feat

- **site:** shared texts in PL/EN/UK: categories, months, regions, durations, status strip, toasts (#58) ([5678315](https://github.com/casper-assistant-ai/alerty-pl/commit/5678315))

## 1.25.0 (2026-11-25)

### feat

- **site:** per-page dictionaries (i18nAdd), tn() plural forms and loc() for PL/EN/UK (#58) ([427df49](https://github.com/casper-assistant-ai/alerty-pl/commit/427df49))

### chore

- **process:** rule for the site-designer's refused patch, ledger of 7 days (#143) ([111a2da](https://github.com/casper-assistant-ai/alerty-pl/commit/111a2da))

## 1.24.1 (2026-11-25)

### fix

- **site:** header source link is a 26 px tap target on phones (#141) ([1e374a0](https://github.com/casper-assistant-ai/alerty-pl/commit/1e374a0))

## 1.24.0 (2026-11-25)

### feat

- **site:** PL/EN/UK base — dictionaries, t() in common.js, language switcher, shared chrome (#128) ([8172103](https://github.com/casper-assistant-ai/alerty-pl/commit/8172103))

### chore

- **process:** the 429 quota outage of 11-25: a rule, a ledger row for the gate's loop, a classifier item (#137) ([cd04f0d](https://github.com/casper-assistant-ai/alerty-pl/commit/cd04f0d))
- **process:** retro 2026-11-25, dev share 66% (#126) ([a7cbc4e](https://github.com/casper-assistant-ai/alerty-pl/commit/a7cbc4e))
- **deps:** drop the temporary Dependabot entry for the dependabot-test branch ([5c71f12](https://github.com/casper-assistant-ai/alerty-pl/commit/5c71f12))

## 1.23.7 (2026-11-25)

### fix

- **site:** send plain-http visitors to https (notifications failed on CORS) ([06d6ff6](https://github.com/casper-assistant-ai/alerty-pl/commit/06d6ff6))
- **parser:** keep one record per alert when gov.pl lists it twice (#123) ([36ff77c](https://github.com/casper-assistant-ai/alerty-pl/commit/36ff77c))

### docs

- **readme:** owner and Dependabot PRs go through the agents' pipeline (#129) ([4543beb](https://github.com/casper-assistant-ai/alerty-pl/commit/4543beb))

### ci

- **pipeline:** put the owner's PRs and Dependabot's PRs through the agents' pipeline ([b7c73ac](https://github.com/casper-assistant-ai/alerty-pl/commit/b7c73ac))

### chore

- **process:** ledger of 7 days: PR #118 on main, the 11-25 529 against the fallback models, the retro at 95% of its limit (#130) ([3c46d46](https://github.com/casper-assistant-ai/alerty-pl/commit/3c46d46))

## 1.23.6 (2026-11-25)

### fix

- **retro:** retry a GitHub API 403 or 429 once and fail with one clear line (#120) ([3e2ce15](https://github.com/casper-assistant-ai/alerty-pl/commit/3e2ce15))

### chore

- **process:** rules for outputs sent before a 529 and the region-keeper bound, ledger of 7 days (#118) ([7b12da2](https://github.com/casper-assistant-ai/alerty-pl/commit/7b12da2))

## 1.23.5 (2026-11-24)

### fix

- **process:** name step-limit timeouts and drop the handler mirror in agent_failures (#112) ([7f814c6](https://github.com/casper-assistant-ai/alerty-pl/commit/7f814c6))

## 1.23.4 (2026-11-24)

### fix

- **agent-health:** recheck agents with open issues on every workflow_run event; the :17/:47 schedule is often skipped for hours ([6be9149](https://github.com/casper-assistant-ai/alerty-pl/commit/6be9149))

## 1.23.3 (2026-11-24)

### fix

- **map:** take the FIRMS fires from GIBS WMS again; WMTS served no FIRMS tile (#100) (#106) ([7627b70](https://github.com/casper-assistant-ai/alerty-pl/commit/7627b70))

### chore

- **process:** rules for the site-fixer timeouts and the pr-fixer patch size, ledger of 7 days (#108) ([88ce945](https://github.com/casper-assistant-ai/alerty-pl/commit/88ce945))

## 1.23.2 (2026-11-24)

### fix

- **agents:** agent-health keeps the process-doctor's closures; docs-keeper gets 20 minutes (#107) ([f5ea7cc](https://github.com/casper-assistant-ai/alerty-pl/commit/f5ea7cc))

### chore

- **process:** ledger, step-limit rule and log-reading item (#99) ([f185f5d](https://github.com/casper-assistant-ai/alerty-pl/commit/f185f5d))

## 1.23.1 (2026-11-24)

### fix

- **rcb:** skip gov.pl's home page served for an alert, so the live service stops re-sending its end ([a8d9532](https://github.com/casper-assistant-ai/alerty-pl/commit/a8d9532))

## 1.23.0 (2026-11-24)

### feat

- **agents:** the process-doctor looks again every 4 h while its issues stay open ([80e7bfe](https://github.com/casper-assistant-ai/alerty-pl/commit/80e7bfe))

### fix

- **site-check:** no second site-fixer while one still runs (#98) ([bfbac04](https://github.com/casper-assistant-ai/alerty-pl/commit/bfbac04))

## 1.22.1 (2026-11-24)

### fix

- **agents:** issues really close, and the process-doctor reads failed runs' logs ([364a1a9](https://github.com/casper-assistant-ai/alerty-pl/commit/364a1a9))
- **map:** take the FIRMS fires from GIBS WMTS and say when a tile fails (#94) ([e551d88](https://github.com/casper-assistant-ai/alerty-pl/commit/e551d88))

## 1.22.0 (2026-11-24)

### feat

- **agents:** process-doctor fixes the agents' process from their failures ([4c44f92](https://github.com/casper-assistant-ai/alerty-pl/commit/4c44f92))

## 1.21.3 (2026-11-24)

### fix

- **agents:** agent-health retires gh-aw's old failure issues and the Detection Runs tracker ([6816fb1](https://github.com/casper-assistant-ai/alerty-pl/commit/6816fb1))

## 1.21.2 (2026-11-24)

### fix

- **agents:** one self-closing health issue per failing agent instead of an issue per failure ([fccf91c](https://github.com/casper-assistant-ai/alerty-pl/commit/fccf91c))
- **process:** keep gh-aw's Detection Runs tracker out of the issue-worker queue (#91) ([ffbfd3c](https://github.com/casper-assistant-ai/alerty-pl/commit/ffbfd3c))

### chore

- **process:** retro 2026-11-24, dev share 64% (#93) ([80f85f6](https://github.com/casper-assistant-ai/alerty-pl/commit/80f85f6))

## 1.21.1 (2026-11-24)

### fix

- **agents:** fall back to glm-5.3/glm-5.1 and let Claude Code retry when z.ai answers 529 ([acb72e9](https://github.com/casper-assistant-ai/alerty-pl/commit/acb72e9))

## 1.21.0 (2026-11-23)

### feat

- **history:** accept a period ?od=&do= and carry it from the map's links (#71) ([2d47c05](https://github.com/casper-assistant-ai/alerty-pl/commit/2d47c05))

### fix

- **site:** count the live service apart from tile servers in the site check (#72) ([305c1cd](https://github.com/casper-assistant-ai/alerty-pl/commit/305c1cd))
- **server:** allow CORS from alerty.klioba.com and link the site there ([19de32a](https://github.com/casper-assistant-ai/alerty-pl/commit/19de32a))
- **process:** take dev-tasks at once instead of after 12 hours ([456a65d](https://github.com/casper-assistant-ai/alerty-pl/commit/456a65d))

## 1.20.2 (2026-11-23)

### fix

- **site:** keep the regex escapes of the site check's page checks (#67) ([b980f41](https://github.com/casper-assistant-ai/alerty-pl/commit/b980f41))

## 1.20.1 (2026-11-23)

### fix

- **ci:** quote the node test step name so ci.yml is valid YAML again ([025b3be](https://github.com/casper-assistant-ai/alerty-pl/commit/025b3be))
- **daily-status:** let the Claude engine run its shell tools with arguments ([3222448](https://github.com/casper-assistant-ai/alerty-pl/commit/3222448))

### chore

- **agents:** give the three watchers 20 minutes on GLM-5.4 ([aeacd71](https://github.com/casper-assistant-ai/alerty-pl/commit/aeacd71))
- **agents:** move ci-doctor, daily-status and issue-triage from Copilot to GLM-5.4 ([f236fb9](https://github.com/casper-assistant-ai/alerty-pl/commit/f236fb9))

## 1.20.0 (2026-11-23)

### feat

- **map:** links to a place and an Esri image, side-by-side image comparison ([108286f](https://github.com/casper-assistant-ai/alerty-pl/commit/108286f))

## 1.19.0 (2026-11-23)

### feat

- **process:** give-up ladder for issues the agents cannot solve ([6c95b7b](https://github.com/casper-assistant-ai/alerty-pl/commit/6c95b7b))

## 1.18.2 (2026-11-23)

### fix

- **map:** ignore impossible dates in the period URL and test the period logic ([e98fe93](https://github.com/casper-assistant-ai/alerty-pl/commit/e98fe93))

### test

- **parser:** pin the status clock, update splitting, list edges and what update() keeps ([82aa7b4](https://github.com/casper-assistant-ai/alerty-pl/commit/82aa7b4))
- **changelog:** cover the LEGACY hand-mapping of prose commits (#59) ([4890bda](https://github.com/casper-assistant-ai/alerty-pl/commit/4890bda))

### ci

- run every node test file in its own step ([eab8920](https://github.com/casper-assistant-ai/alerty-pl/commit/eab8920))
- **security:** security-fixer agent closes Security and quality alerts ([57c284e](https://github.com/casper-assistant-ai/alerty-pl/commit/57c284e))
- make the Dependabot config valid and map its web-editor commit ([845fd66](https://github.com/casper-assistant-ai/alerty-pl/commit/845fd66))
- weekly Dependabot checks ([8253358](https://github.com/casper-assistant-ai/alerty-pl/commit/8253358))

### chore

- **agents:** move the z.ai agents from GLM-5.3 to GLM-5.4 ([a9cc367](https://github.com/casper-assistant-ai/alerty-pl/commit/a9cc367))
- no AI co-author lines in commits; SHA references after the history rewrite ([d164ea9](https://github.com/casper-assistant-ai/alerty-pl/commit/d164ea9))

## 1.18.1 (2026-11-23)

### fix

- **history:** stop the sticky month heading covering row links on touch (#54) ([0b220b9](https://github.com/casper-assistant-ai/alerty-pl/commit/0b220b9))

## 1.18.0 (2026-11-23)

### feat

- **site:** show the hour and minute of every release and change (#50) ([ef1dae9](https://github.com/casper-assistant-ai/alerty-pl/commit/ef1dae9))

### test

- **parser:** a failing page keeps the old archive entries (#51) ([4a42234](https://github.com/casper-assistant-ai/alerty-pl/commit/4a42234))

### chore

- **process:** retro 2026-11-23, dev share 69% (#53) ([9ff948d](https://github.com/casper-assistant-ai/alerty-pl/commit/9ff948d))

## 1.17.6 (2026-11-23)

### fix

- **map:** retry vendored Leaflet once when its first load is dropped (#47) ([21ebef8](https://github.com/casper-assistant-ai/alerty-pl/commit/21ebef8))

## 1.17.5 (2026-11-23)

### fix

- **mobile:** the tab menu scrolls only sideways, not up and down ([b5dde9b](https://github.com/casper-assistant-ai/alerty-pl/commit/b5dde9b))

## 1.17.4 (2026-11-23)

### fix

- **mobile-audit:** stop the click round when a button leaves the page ([9b1468f](https://github.com/casper-assistant-ai/alerty-pl/commit/9b1468f))

## 1.17.3 (2026-11-23)

### fix

- **mobile:** phone audit fixes and a mobile audit in the site check ([d90ad86](https://github.com/casper-assistant-ai/alerty-pl/commit/d90ad86))

## 1.17.2 (2026-11-22)

### fix

- **shelters:** say where to unblock location when the phone does not ask ([ec944f4](https://github.com/casper-assistant-ai/alerty-pl/commit/ec944f4))

### test

- **parser:** cover the chemical and other categories (#33) ([f778424](https://github.com/casper-assistant-ai/alerty-pl/commit/f778424))

### ci

- catch broken HTML and raw markup on the live site ([849df9c](https://github.com/casper-assistant-ai/alerty-pl/commit/849df9c))

## 1.17.1 (2026-11-22)

### fix

- **map:** incursions start where they were launched; Ukraine only as transit ([7cde305](https://github.com/casper-assistant-ai/alerty-pl/commit/7cde305))

## 1.17.0 (2026-11-22)

### feat

- **map:** animate missile and drone incursions into Poland; red days on the slider ([b23b571](https://github.com/casper-assistant-ai/alerty-pl/commit/b23b571))

## 1.16.0 (2026-11-22)

### feat

- **shelters:** map of shelter points with the nearest ones and navigation ([8ebd096](https://github.com/casper-assistant-ai/alerty-pl/commit/8ebd096))

## 1.15.0 (2026-11-22)

### feat

- **map:** pick a period instead of a day; Wayback follows its end ([5e29b44](https://github.com/casper-assistant-ai/alerty-pl/commit/5e29b44))
- **map:** filter the map to one category from the legend (#29) ([0db5659](https://github.com/casper-assistant-ai/alerty-pl/commit/0db5659))

### fix

- **live:** name test alerts' area as a trial ([cbc6c15](https://github.com/casper-assistant-ai/alerty-pl/commit/cbc6c15))

### docs

- complete the team roster and the geo data notes (#27) ([fe73822](https://github.com/casper-assistant-ai/alerty-pl/commit/fe73822))
- **agents:** three learned rules from the first week of agent runs (#28) ([414d6a8](https://github.com/casper-assistant-ai/alerty-pl/commit/414d6a8))

## 1.14.0 (2026-11-22)

### feat

- **live:** alerts within seconds, with Telegram, e-mail and Web Push ([251b5ee](https://github.com/casper-assistant-ai/alerty-pl/commit/251b5ee))

### fix

- **live:** load common.js outside a browser too ([bbaedad](https://github.com/casper-assistant-ai/alerty-pl/commit/bbaedad))

### ci

- start the live service in CI; update data every 30 min ([7aac9cd](https://github.com/casper-assistant-ai/alerty-pl/commit/7aac9cd))

## 1.13.1 (2026-11-22)

### fix

- **agents:** the PR gate sends a conflicting PR to the fixer ([db24990](https://github.com/casper-assistant-ai/alerty-pl/commit/db24990))
- **agents:** the PR reviewer rejects behaviour-free churn even when an issue asks for it ([a0c09ae](https://github.com/casper-assistant-ai/alerty-pl/commit/a0c09ae))
- **agents:** the PR gate waits for the reviewer and fixer it starts ([b617566](https://github.com/casper-assistant-ai/alerty-pl/commit/b617566))

### test

- **site:** cover the common.js date and category helpers with node (#22) ([3e6de5b](https://github.com/casper-assistant-ai/alerty-pl/commit/3e6de5b))

### chore

- **process:** retro 2026-11-22, dev share 70% (#26) ([57589b7](https://github.com/casper-assistant-ai/alerty-pl/commit/57589b7))

## 1.13.0 (2026-11-22)

### feat

- **agents:** PR fixer repairs agent PRs in their own branch before the gate gives up ([7106619](https://github.com/casper-assistant-ai/alerty-pl/commit/7106619))

## 1.12.0 (2026-11-22)

### feat

- **site:** show powiat and gmina names for each alert ([4674c53](https://github.com/casper-assistant-ai/alerty-pl/commit/4674c53))

## 1.11.0 (2026-11-22)

### feat

- **agents:** PR reviewer agent; gate merges or closes every agent PR itself ([4a7ffeb](https://github.com/casper-assistant-ai/alerty-pl/commit/4a7ffeb))

### test

- **parser:** cover nationwide drill, fire alert and multi-update alerts (#18) ([19b10dd](https://github.com/casper-assistant-ai/alerty-pl/commit/19b10dd))

## 1.10.2 (2026-11-22)

### fix

- **agents:** CI doctor reads job logs of pull request runs ([377c6a0](https://github.com/casper-assistant-ai/alerty-pl/commit/377c6a0))

## 1.10.1 (2026-11-22)

### fix

- **agents:** let workflows started by github-actions[bot] activate the agents ([ff94c01](https://github.com/casper-assistant-ai/alerty-pl/commit/ff94c01))

## 1.10.0 (2026-11-22)

### feat

- **site:** cross-link analytics rankings to history with a powiat filter (#15) ([41acfba](https://github.com/casper-assistant-ai/alerty-pl/commit/41acfba))

### fix

- **agents:** count the worker's daily improvement by a visible first line ([4c5c008](https://github.com/casper-assistant-ai/alerty-pl/commit/4c5c008))
- **agents:** gate closes the issues a merged agent PR fixes; audit timeout 40 min ([87772c5](https://github.com/casper-assistant-ai/alerty-pl/commit/87772c5))

### test

- **changelog:** cover lint subjects and the next version number (#16) ([fe3251e](https://github.com/casper-assistant-ai/alerty-pl/commit/fe3251e))
- **parser:** cover status TTL, drill windows and weather/ordnance/drill alerts (#13) ([31b79ac](https://github.com/casper-assistant-ai/alerty-pl/commit/31b79ac))

### ci

- **gate:** approve the waiting CI runs of agent PRs ([bd29b9a](https://github.com/casper-assistant-ai/alerty-pl/commit/bd29b9a))

### chore

- **process:** needs a maintainer - raise security-auditor timeout to 40 (#14) ([b873a13](https://github.com/casper-assistant-ai/alerty-pl/commit/b873a13))

## 1.9.0 (2026-11-22)

### feat

- **agents:** issue-worker takes every issue to a PR or a reasoned close ([e445301](https://github.com/casper-assistant-ai/alerty-pl/commit/e445301))
- **process:** run process-retro daily over a rolling 7-day window ([dae062f](https://github.com/casper-assistant-ai/alerty-pl/commit/dae062f))

### chore

- **process:** retro 2026-11-21, dev share 60% (#12) ([51b1cc9](https://github.com/casper-assistant-ai/alerty-pl/commit/51b1cc9))

## 1.8.1 (2026-11-21)

### fix

- **process:** count agent-coach and process-retro as process agents, not builders ([4dffb32](https://github.com/casper-assistant-ai/alerty-pl/commit/4dffb32))

### chore

- **process:** retro 2026-11-21, dev share 60% (#11) ([5615b11](https://github.com/casper-assistant-ai/alerty-pl/commit/5615b11))

## 1.8.0 (2026-11-21)

### feat

- **process:** weekly process-retro agent that keeps the team developing ([e2139c1](https://github.com/casper-assistant-ai/alerty-pl/commit/e2139c1))

## 1.7.0 (2026-11-21)

### feat

- **map:** day slider, Esri Wayback and NASA imagery, NASA FIRMS fires ([1f885b6](https://github.com/casper-assistant-ai/alerty-pl/commit/1f885b6))

## 1.6.0 (2026-11-21)

### feat

- **site-check:** hourly headless check of the live site and a site-fixer agent ([95da703](https://github.com/casper-assistant-ai/alerty-pl/commit/95da703))
- **changelog:** Zmiany page with semver releases built from Conventional Commits ([eb060fc](https://github.com/casper-assistant-ai/alerty-pl/commit/eb060fc))

## 1.5.1 (2026-11-21)

### fix

- **regions:** re-parse cached alerts after the Warsaw-area town rules (#7) ([e9f75cb](https://github.com/casper-assistant-ai/alerty-pl/commit/e9f75cb))

## 1.5.0 (2026-11-21)

### feat

- alert history since 2021, analytics page and a redesign ([040db28](https://github.com/casper-assistant-ai/alerty-pl/commit/040db28))

## 1.4.0 (2026-11-21)

### feat

- **site:** honest status signals, reduced-motion opt-in, live-region alarm announcements (#5) ([1fdd28c](https://github.com/casper-assistant-ai/alerty-pl/commit/1fdd28c))

## 1.3.0 (2026-11-21)

### feat

- **regions:** map Warsaw-area towns to powiaty (#4) ([6313095](https://github.com/casper-assistant-ai/alerty-pl/commit/6313095))

## 1.2.0 (2026-11-21)

### feat

- **agents:** developer agents on z.ai (GLM-5.3) with the site-designer, security-auditor and agent-coach skills ([eb8df96](https://github.com/casper-assistant-ai/alerty-pl/commit/eb8df96))

## 1.1.1 (2026-11-21)

### fix

- **deploy:** retry the Pages deploy when the artifact is not listed yet ([1d7350e](https://github.com/casper-assistant-ai/alerty-pl/commit/1d7350e))

## 1.1.0 (2026-11-21)

### feat

- **monitoring:** agent monitoring with gh-cao, alert times in the history fixed ([ef40b0f](https://github.com/casper-assistant-ai/alerty-pl/commit/ef40b0f))

## 1.0.1 (2026-11-21)

### fix

- **update:** autostash meta.json before the rebase ([c2871d9](https://github.com/casper-assistant-ai/alerty-pl/commit/c2871d9))

## 1.0.0 (2026-11-21)

### feat

- alert map of Poland from gov.pl RCB, run by an agent team ([0b213ac](https://github.com/casper-assistant-ai/alerty-pl/commit/0b213ac))
