// tests/site_check.test.mjs — the page checks of scripts/site_check.mjs are template literals that
// run in the browser, so a regex inside one writes its backslashes twice: \. alone is eaten by the
// template and \? becomes a quantifier, which made the hourly site check report a missing
// «Porównaj daty» link on a page that had it (#61).
import { readFileSync } from "node:fs";
import { test } from "node:test";
import assert from "node:assert/strict";

const src = readFileSync(new URL("../scripts/site_check.mjs", import.meta.url), "utf8");

// COMMON, MARKUP and every page's check, as the source spells them between the backticks
const templates = [...src.matchAll(/(?:const (COMMON|MARKUP) = |check: )`((?:[^`\\]|\\.)*)`/g)].map((m) => {
  const names = [...src.slice(0, m.index).matchAll(/name: "([^"]*)"/g)];
  return { name: m[1] || names[names.length - 1][1], raw: m[2] };
});
// the string the browser receives: the template literal evaluated
const inPage = (t) => new Function("return (`" + t.raw + "`)")();
// one check run against a stub page: querySelector answers from the map, location is the address
const run = (code, els, search) => {
  globalThis.document = { querySelector: (s) => els[s] ?? null };
  globalThis.location = { search };
  return new Function("return (" + code + ")")();
};

test("COMMON, MARKUP and every page check are read from the script", () => {
  assert.equal(templates.length, (src.match(/check: `/g) || []).length + 2);
  for (const t of templates) assert.ok(t.name && t.raw.includes("(() =>"), t.name);
});

test("a regex in a page template writes its backslashes twice, so the browser keeps them", () => {
  // in a template literal \. is just "." and \? is just "?", which in a regex quantifies the
  // letter before it: /porownaj.html?srodek=/ can never match a real link
  for (const t of templates) {
    assert.doesNotMatch(t.raw, /(?<!\\)\\(?!\\)/,
      `${t.name}: a lone backslash in the template is dropped; write two to get one in the page`);
  }
});

test("every check compiles as the browser reads it", () => {
  for (const t of templates) assert.doesNotThrow(() => new Function("return (" + inPage(t) + ")"), t.name);
});

test("the «Porównaj daty» check passes on the link the map page builds, and still catches a missing one", () => {
  const t = templates.find((x) => x.name.startsWith("Mapa, link do miejsca"));
  assert.ok(t, "the page check of the link to a place and its picture is gone");
  const code = inPage(t);
  assert.ok(code.includes("/porownaj\\.html\\?srodek=/"), "the browser must receive the escapes of /porownaj\\.html\\?srodek=/");
  const search = "?podklad=esri&srodek=50.5650,17.9650&zoom=15&zdjecie=2025-04-24";
  const els = {
    "#wayback option:checked": { textContent: "zdjęcie z 24.04.2025" },
    // what compareLink() in docs/app.js writes for this view
    "#compare": { href: "https://casper-assistant-ai.github.io/alerty-pl/porownaj.html?srodek=50.56500%2C17.96500&zoom=15&lewa=2025-03-27&prawa=2025-04-24" },
  };
  assert.deepEqual(run(code, els, search), []);
  assert.deepEqual(run(code, { ...els, "#compare": { href: "porownaj.html" } }, search), ["the «Porównaj daty» link is missing"]);
  assert.deepEqual(run(code, { ...els, "#compare": null }, search), ["the «Porównaj daty» link is missing"]);
});
