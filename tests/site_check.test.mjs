// tests/site_check.test.mjs — the page checks of scripts/site_check.mjs as the browser receives them.
// Alone: node --test tests/site_check.test.mjs ; CI runs every tests/*.test.mjs in its "Node tests" step.
import { readFileSync } from "node:fs";
import { test } from "node:test";
import assert from "node:assert/strict";
import { COMMON, MARKUP, PAGES } from "../scripts/site_check.mjs";

const ORIGIN = "https://casper-assistant-ai.github.io/alerty-pl/";
// a check runs against the smallest page it reads: querySelector(sel) answers from nodes, else null
function run(check, nodes = {}, search = "") {
  const document = { querySelector: (sel) => nodes[sel] ?? null, querySelectorAll: () => [] };
  return new Function("document", "location", "innerWidth", "scrollY", `return ${check};`)(document, { search }, 1440, 0);
}

const LINK = PAGES.find((p) => p.path.includes("zdjecie="));
const VIEW = "?podklad=esri&srodek=50.5650,17.9650&zoom=15&zdjecie=2025-04-24";
// what compareLink() of docs/app.js sets; the browser answers .href with the absolute URL
const COMPARE = ORIGIN + "porownaj.html?srodek=50.56500%2C17.96500&zoom=15&lewa=2025-03-27&prawa=2025-04-24";
const PICKED = { "#wayback option:checked": { textContent: "zdjęcie z 24.04.2025" } };

test("the link-to-a-place check accepts the page docs/app.js builds (#61)", () => {
  assert.ok(LINK, "the «Mapa, link do miejsca i zdjęcia» page check is gone");
  assert.deepEqual(run(LINK.check, { ...PICKED, "#compare": { href: COMPARE } }, VIEW), []);
  // before the archive of this spot has two images, the link has no lewa/prawa
  assert.deepEqual(run(LINK.check, { ...PICKED, "#compare": { href: COMPARE.replace(/&lewa=.*$/, "") } }, VIEW), []);
});

test("and still reports a link never set, another release and a view missing from the URL", () => {
  const staticHref = { ...PICKED, "#compare": { href: ORIGIN + "porownaj.html" } }; // the href of docs/index.html
  assert.deepEqual(run(LINK.check, staticHref, VIEW), ["the «Porównaj daty» link is missing"]);
  assert.deepEqual(run(LINK.check, PICKED, VIEW), ["the «Porównaj daty» link is missing"]);
  const other = { "#wayback option:checked": { textContent: "zdjęcie z 26.11.2026" }, "#compare": { href: COMPARE } };
  assert.deepEqual(run(LINK.check, other, "?podklad=esri"),
    ["?zdjecie=2025-04-24 did not pick the Esri release of 24.04.2025", "the view is not in the URL (srodek, zoom)"]);
});

test("every check is valid JavaScript once the template literal is cooked", () => {
  for (const check of [COMMON, MARKUP, ...PAGES.map((p) => p.check)]) {
    assert.doesNotThrow(() => new Function("document", "location", `return ${check};`), check.slice(0, 60));
  }
});

test("every backslash of the checks is written twice, so the template literal keeps it", () => {
  // COMMON, MARKUP and the page checks are template literals, and a template eats the backslash before
  // anything but an escape sequence: "\?" reached the page as "?", /porownaj\.html\?srodek=/ became
  // /porownaj.html?srodek=/ with a quantifier on the "l", and the site check reported a missing
  // «Porównaj daty» link on every run (issue #61). Written "\\", it arrives as "\".
  const src = readFileSync(new URL("../scripts/site_check.mjs", import.meta.url), "utf8");
  const from = src.indexOf("const COMMON = `"), to = src.indexOf("\n];", src.indexOf("const PAGES = ["));
  assert.ok(from !== -1 && to > from, "the checks moved in scripts/site_check.mjs: update this test");
  const singles = [];
  for (let i = from; i < to; i++) if (src[i] === "\\") { if (src[i + 1] === "\\") i++; else singles.push(src.slice(i, i + 12)); }
  assert.deepEqual(singles, [], "a single backslash in a check is eaten before the browser sees the regex");
});
