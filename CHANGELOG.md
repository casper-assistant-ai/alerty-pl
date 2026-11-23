# Changelog

Built by `scripts/changelog.py` from [Conventional Commits](https://www.conventionalcommits.org) and the version tags; versions follow [semver](https://semver.org). Do not edit by hand.

## Unreleased

### ci

- make the Dependabot config valid and map its web-editor commit ([be7bc8c](https://github.com/casper-assistant-ai/alerty-pl/commit/be7bc8c))
- weekly Dependabot checks ([7f096cc](https://github.com/casper-assistant-ai/alerty-pl/commit/7f096cc))

## 1.18.1 (2026-11-23)

### fix

- **history:** stop the sticky month heading covering row links on touch (#54) ([8c1aa7e](https://github.com/casper-assistant-ai/alerty-pl/commit/8c1aa7e))

## 1.18.0 (2026-11-23)

### feat

- **site:** show the hour and minute of every release and change (#50) ([c329fef](https://github.com/casper-assistant-ai/alerty-pl/commit/c329fef))

### test

- **parser:** a failing page keeps the old archive entries (#51) ([c2f3e5f](https://github.com/casper-assistant-ai/alerty-pl/commit/c2f3e5f))

### chore

- **process:** retro 2026-11-23, dev share 69% (#53) ([793006f](https://github.com/casper-assistant-ai/alerty-pl/commit/793006f))

## 1.17.6 (2026-11-23)

### fix

- **map:** retry vendored Leaflet once when its first load is dropped (#47) ([14c5021](https://github.com/casper-assistant-ai/alerty-pl/commit/14c5021))

## 1.17.5 (2026-11-23)

### fix

- **mobile:** the tab menu scrolls only sideways, not up and down ([61dde92](https://github.com/casper-assistant-ai/alerty-pl/commit/61dde92))

## 1.17.4 (2026-11-23)

### fix

- **mobile-audit:** stop the click round when a button leaves the page ([8103aa7](https://github.com/casper-assistant-ai/alerty-pl/commit/8103aa7))

## 1.17.3 (2026-11-23)

### fix

- **mobile:** phone audit fixes and a mobile audit in the site check ([c8f4d4e](https://github.com/casper-assistant-ai/alerty-pl/commit/c8f4d4e))

## 1.17.2 (2026-11-22)

### fix

- **shelters:** say where to unblock location when the phone does not ask ([74fa73a](https://github.com/casper-assistant-ai/alerty-pl/commit/74fa73a))

### test

- **parser:** cover the chemical and other categories (#33) ([9a0605e](https://github.com/casper-assistant-ai/alerty-pl/commit/9a0605e))

### ci

- catch broken HTML and raw markup on the live site ([b95196c](https://github.com/casper-assistant-ai/alerty-pl/commit/b95196c))

## 1.17.1 (2026-11-22)

### fix

- **map:** incursions start where they were launched; Ukraine only as transit ([e7f8ef9](https://github.com/casper-assistant-ai/alerty-pl/commit/e7f8ef9))

## 1.17.0 (2026-11-22)

### feat

- **map:** animate missile and drone incursions into Poland; red days on the slider ([6ebac81](https://github.com/casper-assistant-ai/alerty-pl/commit/6ebac81))

## 1.16.0 (2026-11-22)

### feat

- **shelters:** map of shelter points with the nearest ones and navigation ([94a3059](https://github.com/casper-assistant-ai/alerty-pl/commit/94a3059))

## 1.15.0 (2026-11-22)

### feat

- **map:** pick a period instead of a day; Wayback follows its end ([ca2cba3](https://github.com/casper-assistant-ai/alerty-pl/commit/ca2cba3))
- **map:** filter the map to one category from the legend (#29) ([4694989](https://github.com/casper-assistant-ai/alerty-pl/commit/4694989))

### fix

- **live:** name test alerts' area as a trial ([7aa1064](https://github.com/casper-assistant-ai/alerty-pl/commit/7aa1064))

### docs

- complete the team roster and the geo data notes (#27) ([5ca5717](https://github.com/casper-assistant-ai/alerty-pl/commit/5ca5717))
- **agents:** three learned rules from the first week of agent runs (#28) ([712ddc4](https://github.com/casper-assistant-ai/alerty-pl/commit/712ddc4))

## 1.14.0 (2026-11-22)

### feat

- **live:** alerts within seconds, with Telegram, e-mail and Web Push ([0423ed9](https://github.com/casper-assistant-ai/alerty-pl/commit/0423ed9))

### fix

- **live:** load common.js outside a browser too ([4054612](https://github.com/casper-assistant-ai/alerty-pl/commit/4054612))

### ci

- start the live service in CI; update data every 30 min ([13337a4](https://github.com/casper-assistant-ai/alerty-pl/commit/13337a4))

## 1.13.1 (2026-11-22)

### fix

- **agents:** the PR gate sends a conflicting PR to the fixer ([3a4fc42](https://github.com/casper-assistant-ai/alerty-pl/commit/3a4fc42))
- **agents:** the PR reviewer rejects behaviour-free churn even when an issue asks for it ([9ae99f9](https://github.com/casper-assistant-ai/alerty-pl/commit/9ae99f9))
- **agents:** the PR gate waits for the reviewer and fixer it starts ([75d0e41](https://github.com/casper-assistant-ai/alerty-pl/commit/75d0e41))

### test

- **site:** cover the common.js date and category helpers with node (#22) ([7bf415c](https://github.com/casper-assistant-ai/alerty-pl/commit/7bf415c))

### chore

- **process:** retro 2026-11-22, dev share 70% (#26) ([83e04d6](https://github.com/casper-assistant-ai/alerty-pl/commit/83e04d6))

## 1.13.0 (2026-11-22)

### feat

- **agents:** PR fixer repairs agent PRs in their own branch before the gate gives up ([29d36d3](https://github.com/casper-assistant-ai/alerty-pl/commit/29d36d3))

## 1.12.0 (2026-11-22)

### feat

- **site:** show powiat and gmina names for each alert ([967a236](https://github.com/casper-assistant-ai/alerty-pl/commit/967a236))

## 1.11.0 (2026-11-22)

### feat

- **agents:** PR reviewer agent; gate merges or closes every agent PR itself ([143adb0](https://github.com/casper-assistant-ai/alerty-pl/commit/143adb0))

### test

- **parser:** cover nationwide drill, fire alert and multi-update alerts (#18) ([09eeeb6](https://github.com/casper-assistant-ai/alerty-pl/commit/09eeeb6))

## 1.10.2 (2026-11-22)

### fix

- **agents:** CI doctor reads job logs of pull request runs ([05d68cc](https://github.com/casper-assistant-ai/alerty-pl/commit/05d68cc))

## 1.10.1 (2026-11-22)

### fix

- **agents:** let workflows started by github-actions[bot] activate the agents ([c62710e](https://github.com/casper-assistant-ai/alerty-pl/commit/c62710e))

## 1.10.0 (2026-11-22)

### feat

- **site:** cross-link analytics rankings to history with a powiat filter (#15) ([c1d2cae](https://github.com/casper-assistant-ai/alerty-pl/commit/c1d2cae))

### fix

- **agents:** count the worker's daily improvement by a visible first line ([642d0ad](https://github.com/casper-assistant-ai/alerty-pl/commit/642d0ad))
- **agents:** gate closes the issues a merged agent PR fixes; audit timeout 40 min ([7b49a1e](https://github.com/casper-assistant-ai/alerty-pl/commit/7b49a1e))

### test

- **changelog:** cover lint subjects and the next version number (#16) ([561e2ad](https://github.com/casper-assistant-ai/alerty-pl/commit/561e2ad))
- **parser:** cover status TTL, drill windows and weather/ordnance/drill alerts (#13) ([8d9d5d1](https://github.com/casper-assistant-ai/alerty-pl/commit/8d9d5d1))

### ci

- **gate:** approve the waiting CI runs of agent PRs ([5a1de20](https://github.com/casper-assistant-ai/alerty-pl/commit/5a1de20))

### chore

- **process:** needs a maintainer - raise security-auditor timeout to 40 (#14) ([6c97686](https://github.com/casper-assistant-ai/alerty-pl/commit/6c97686))

## 1.9.0 (2026-11-22)

### feat

- **agents:** issue-worker takes every issue to a PR or a reasoned close ([7eb6301](https://github.com/casper-assistant-ai/alerty-pl/commit/7eb6301))
- **process:** run process-retro daily over a rolling 7-day window ([3d7397b](https://github.com/casper-assistant-ai/alerty-pl/commit/3d7397b))

### chore

- **process:** retro 2026-11-21, dev share 60% (#12) ([42eaad0](https://github.com/casper-assistant-ai/alerty-pl/commit/42eaad0))

## 1.8.1 (2026-11-21)

### fix

- **process:** count agent-coach and process-retro as process agents, not builders ([921dddd](https://github.com/casper-assistant-ai/alerty-pl/commit/921dddd))

### chore

- **process:** retro 2026-11-21, dev share 60% (#11) ([2d5145a](https://github.com/casper-assistant-ai/alerty-pl/commit/2d5145a))

## 1.8.0 (2026-11-21)

### feat

- **process:** weekly process-retro agent that keeps the team developing ([33c96fe](https://github.com/casper-assistant-ai/alerty-pl/commit/33c96fe))

## 1.7.0 (2026-11-21)

### feat

- **map:** day slider, Esri Wayback and NASA imagery, NASA FIRMS fires ([49e5f4a](https://github.com/casper-assistant-ai/alerty-pl/commit/49e5f4a))

## 1.6.0 (2026-11-21)

### feat

- **site-check:** hourly headless check of the live site and a site-fixer agent ([ffe1c84](https://github.com/casper-assistant-ai/alerty-pl/commit/ffe1c84))
- **changelog:** Zmiany page with semver releases built from Conventional Commits ([c39f61e](https://github.com/casper-assistant-ai/alerty-pl/commit/c39f61e))

## 1.5.1 (2026-11-21)

### fix

- **regions:** re-parse cached alerts after the Warsaw-area town rules (#7) ([480d5db](https://github.com/casper-assistant-ai/alerty-pl/commit/480d5db))

## 1.5.0 (2026-11-21)

### feat

- alert history since 2021, analytics page and a redesign ([d20eeb2](https://github.com/casper-assistant-ai/alerty-pl/commit/d20eeb2))

## 1.4.0 (2026-11-21)

### feat

- **site:** honest status signals, reduced-motion opt-in, live-region alarm announcements (#5) ([4f96f72](https://github.com/casper-assistant-ai/alerty-pl/commit/4f96f72))

## 1.3.0 (2026-11-21)

### feat

- **regions:** map Warsaw-area towns to powiaty (#4) ([99f7d21](https://github.com/casper-assistant-ai/alerty-pl/commit/99f7d21))

## 1.2.0 (2026-11-21)

### feat

- **agents:** developer agents on z.ai (GLM-5.3) with the site-designer, security-auditor and agent-coach skills ([9876508](https://github.com/casper-assistant-ai/alerty-pl/commit/9876508))

## 1.1.1 (2026-11-21)

### fix

- **deploy:** retry the Pages deploy when the artifact is not listed yet ([518003b](https://github.com/casper-assistant-ai/alerty-pl/commit/518003b))

## 1.1.0 (2026-11-21)

### feat

- **monitoring:** agent monitoring with gh-cao, alert times in the history fixed ([6735655](https://github.com/casper-assistant-ai/alerty-pl/commit/6735655))

## 1.0.1 (2026-11-21)

### fix

- **update:** autostash meta.json before the rebase ([9022420](https://github.com/casper-assistant-ai/alerty-pl/commit/9022420))

## 1.0.0 (2026-11-21)

### feat

- alert map of Poland from gov.pl RCB, run by an agent team ([d9b56f4](https://github.com/casper-assistant-ai/alerty-pl/commit/d9b56f4))
