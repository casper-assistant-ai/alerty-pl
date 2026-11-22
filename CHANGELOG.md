# Changelog

Built by `scripts/changelog.py` from [Conventional Commits](https://www.conventionalcommits.org) and the version tags; versions follow [semver](https://semver.org). Do not edit by hand.

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
