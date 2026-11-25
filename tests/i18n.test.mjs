// Node test for the interface languages (dev-task #125): docs/i18n.js and its use in docs/common.js.
// No npm, just node:test and node:assert; CI runs it through `node --test tests/*.test.mjs`.
import { readFileSync, readdirSync } from "node:fs";
import test from "node:test";
import assert from "node:assert/strict";

const read = (p) => readFileSync(new URL("../" + p, import.meta.url), "utf8");
const PAGES = readdirSync(new URL("../docs", import.meta.url)).filter((f) => f.endsWith(".html")).sort();
const i18n = new Function(`${read("docs/i18n.js")}\n;return I18N;`)();
const CODES = ["pl", "en", "uk"];

// common.js with the dictionaries: a document stub whose querySelectorAll answers per selector, as a page's
// marked elements; `loc` is { search }, `store` a localStorage stub
function load({ search = "", store = {}, doc } = {}) {
  const els = {
    "nav.langs a[data-lang]": ["pl", "en", "uk"].map((l) => ({ dataset: { lang: l }, attrs: {}, setAttribute(k, v) { this.attrs[k] = v; }, removeAttribute(k) { delete this.attrs[k]; } })),
    "[data-i18n]": [{ dataset: { i18n: "src", i18nParamName: "src.psp" } }, { dataset: { i18n: "tab.map" } }],
    "[data-i18n-aria]": [{ dataset: { i18nAria: "nav.tabs" }, setAttribute(k, v) { this.attrs = { [k]: v }; } }],
  };
  const title = { dataset: { i18nTitle: "title.map" } };
  const d = doc || { documentElement: {}, title: "Alerty RCB — mapa alertów w Polsce",
    querySelector: (s) => (s === "title[data-i18n-title]" ? title : null),
    querySelectorAll: (s) => els[s] || [] };
  const store0 = { getItem: (k) => store[k] ?? null, setItem: (k, v) => { store[k] = v; } };
  const RCB = new Function("document", "location", "localStorage", `${read("docs/i18n.js")}\n${read("docs/common.js")}\n;return RCB;`)(d, { search }, store0);
  return { RCB, d, els, store };
}
const text = (html, re) => [...html.matchAll(re)];

test("the three dictionaries have the same keys and no empty text", () => {
  assert.deepEqual(Object.keys(i18n), CODES);
  const keys = Object.keys(i18n.pl).sort();
  assert.ok(keys.length > 40, `${keys.length} keys`);
  for (const c of CODES) {
    assert.deepEqual(Object.keys(i18n[c]).sort(), keys, c);
    for (const [k, v] of Object.entries(i18n[c])) assert.ok(typeof v === "string" && v.trim() && !/[{}]/.test(v.replace(/\{name\}/g, "")), `${c}.${k}`);
  }
  assert.deepEqual(text(i18n.pl.src, /\{(\w+)\}/g).map((m) => m[1]), ["name"]);
});

test("every marked element of every page names a key of all three dictionaries", () => {
  assert.equal(PAGES.length, 7);
  for (const f of PAGES) {
    const html = read("docs/" + f);
    const used = [...text(html, /data-i18n(?:-aria|-title|-param-\w+)?="([^"]+)"/g)].map((m) => m[1]);
    assert.ok(used.length > 15, `${f}: ${used.length} marks`);
    for (const k of used) for (const c of CODES) assert.ok(i18n[c][k] !== undefined, `${f}: ${c} has no ${k}`);
  }
});

test("the Polish dictionary says what each page says", () => {
  for (const f of PAGES) {
    const html = read("docs/" + f);
    for (const [, , before, key, after, txt] of text(html, /<([a-z0-9]+)\s([^<>]*?)\sdata-i18n="([^"]+)"([^<>]*)>([^<]+)<\/\1>/g)) {
      const params = {};
      for (const [, n, k] of text(before + after, /data-i18n-param-(\w+)="([^"]+)"/g)) params[n] = i18n.pl[k];
      assert.equal(i18n.pl[key].replace("{name}", params.name ?? "{name}"), txt, `${f}: ${key}`);
    }
    for (const [, label, key] of text(html, /aria-label="([^"]+)" data-i18n-aria="([^"]+)"/g)) assert.equal(i18n.pl[key], label, `${f}: ${key}`);
    for (const [, key, txt] of text(html, /<title data-i18n-title="([^"]+)">([^<]+)<\/title>/g)) assert.equal(i18n.pl[key], txt, `${f}: ${key}`);
  }
});

test("every page loads i18n.js before common.js and has the switcher", () => {
  for (const f of PAGES) {
    const html = read("docs/" + f);
    assert.ok(html.indexOf('src="i18n.js" defer') < html.indexOf('src="common.js" defer'), f);
    assert.match(html, /<nav class="langs" aria-label="[^"]+" data-i18n-aria="nav\.langs">/);
    assert.deepEqual(text(html, /<a href="\?lang=(\w+)" hreflang="\w+" lang="\w+" data-lang="\w+" aria-label="[^"]+" data-i18n-aria="lang\.\w+"( aria-current="true")?>[A-Z]{2}<\/a>/g).map((m) => m[1]), ["pl", "en", "uk"], f);
    assert.match(html, /<nav class="tabs" aria-label="Strony" data-i18n-aria="nav\.tabs">/);
  }
});

test("lang(): ?lang= first, then the stored choice, then pl; an unknown code is ignored", () => {
  const { RCB } = load();
  assert.equal(RCB.lang("?lang=en", "uk"), "en");
  assert.equal(RCB.lang("", "uk"), "uk");
  assert.equal(RCB.lang("?lang=de", "uk"), "uk"); // unknown in the URL: the stored choice stands
  assert.equal(RCB.lang("?lang=de", "xx"), "pl");
  assert.equal(RCB.lang("", null), "pl");
  assert.equal(RCB.lang("?od=2026-01-01&lang=uk"), "uk");
});

test("lang() reads the URL and localStorage of the page when given nothing", () => {
  assert.equal(load({ search: "?lang=uk" }).RCB.lang(), "uk");
  assert.equal(load({ store: { "alerty-lang": "en" } }).RCB.lang(), "en");
  assert.equal(load({ store: { "alerty-lang": "zz" } }).RCB.lang(), "pl");
  assert.equal(load().RCB.lang(), "pl");
});

test("t() fills {name}, falls back to Polish and leaves a missing key as it is", () => {
  const { RCB } = load({ store: { "alerty-lang": "uk" } });
  assert.equal(RCB.t("src", { name: "gov.pl" }, "en"), "source: gov.pl");
  assert.equal(RCB.t("src", { name: "dane.gov.pl" }), "джерело: dane.gov.pl"); // the page's language
  assert.equal(RCB.t("tab.map", null, "en"), "Map");
  assert.equal(RCB.t("no.such.key", null, "en"), "no.such.key");
});

test("langUrl() keeps every other parameter as it is and sets lang", () => {
  const { RCB } = load();
  const s = "?srodek=50.06140,19.93808&zoom=6.5&od=2026-11-01&do=2026-11-20&podklad=esri&zdjecie=2026-10-01&pozary=1&lang=pl";
  assert.equal(RCB.langUrl(s, "en"), "?srodek=50.06140,19.93808&zoom=6.5&od=2026-11-01&do=2026-11-20&podklad=esri&zdjecie=2026-10-01&pozary=1&lang=en");
  assert.equal(RCB.langUrl("", "uk"), "?lang=uk");
  assert.equal(RCB.langUrl("?lat=52&lon=21", "pl"), "?lat=52&lon=21&lang=pl");
});

test("applyI18n(): a page that chose no language keeps its text, the switcher still points at the other languages", () => {
  const { RCB, d, els } = load({ search: "?zoom=7" });
  assert.equal(RCB.applyI18n(d), "pl");
  assert.equal(d.documentElement.lang, undefined);
  assert.equal(d.title, "Alerty RCB — mapa alertów w Polsce");
  assert.equal(els["[data-i18n]"][0].textContent, undefined);
  const [pl, en, uk] = els["nav.langs a[data-lang]"];
  assert.deepEqual([pl.attrs.href, en.attrs.href, uk.attrs.href], ["?zoom=7&lang=pl", "?zoom=7&lang=en", "?zoom=7&lang=uk"]);
  assert.equal(pl.attrs["aria-current"], "true");
  assert.equal(en.attrs["aria-current"], undefined);
});

test("applyI18n(): ?lang=uk translates the chrome, sets <html lang> and <title>, keeps the choice and marks UK", () => {
  const { RCB, d, els, store } = load({ search: "?lang=uk&srodek=52,21" });
  assert.equal(RCB.applyI18n(d), "uk");
  assert.equal(d.documentElement.lang, "uk");
  assert.equal(d.title, "Алерти RCB — мапа алертів Польщі");
  const [src, tab] = els["[data-i18n]"];
  assert.equal(src.textContent, "джерело: Державна пожежна охорона, dane.gov.pl"); // {name} from data-i18n-param-name
  assert.equal(tab.textContent, "Мапа");
  assert.deepEqual(els["[data-i18n-aria]"][0].attrs, { "aria-label": "Сторінки" });
  assert.equal(els["nav.langs a[data-lang]"][2].attrs["aria-current"], "true");
  assert.equal(els["nav.langs a[data-lang]"][2].attrs.href, "?srodek=52,21&lang=uk");
  assert.equal(store["alerty-lang"], "uk");
});

test("without docs/i18n.js common.js still loads and t() gives the key back", () => {
  const RCB = new Function("document", `${read("docs/common.js")}\n;return RCB;`)({ querySelector: () => null });
  assert.equal(RCB.lang("", "en"), "en");
  assert.equal(RCB.t("tab.map", null, "en"), "tab.map");
  assert.equal(RCB.applyI18n({ querySelector: () => null }), "pl");
});
