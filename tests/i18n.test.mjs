// Node test for the interface languages (dev-task #125): docs/i18n.js and its use in docs/common.js.
// No npm, just node:test and node:assert; CI runs it through `node --test tests/*.test.mjs`.
import { readFileSync, readdirSync } from "node:fs";
import test from "node:test";
import assert from "node:assert/strict";

const read = (p) => readFileSync(new URL("../" + p, import.meta.url), "utf8");
const PAGES = readdirSync(new URL("../docs", import.meta.url)).filter((f) => f.endsWith(".html")).sort();
// docs/i18n.js and every page's docs/i18n-<page>.js, as the pages load them
const DICTS = ["i18n.js", ...readdirSync(new URL("../docs", import.meta.url)).filter((f) => /^i18n-[\w-]+\.js$/.test(f)).sort()]
  .map((f) => read("docs/" + f)).join("\n");
const i18n = new Function(`${DICTS}\n;return I18N;`)();
const CODES = ["pl", "en", "uk"];

// common.js with the dictionaries: a document stub whose querySelectorAll answers per selector, as a page's
// marked elements; `loc` is the { search } of the page's location (a test may rewrite it, as the pages do), `store`
// a localStorage stub. The nav records its listeners as a browser does: the same callback for one type is added once.
function load({ search = "", store = {}, doc } = {}) {
  const link = (l) => ({ dataset: { lang: l }, attrs: {}, setAttribute(k, v) { this.attrs[k] = v; }, removeAttribute(k) { delete this.attrs[k]; },
    closest(s) { return s === "a[data-lang]" ? this : null; } });
  const nav = { listeners: {}, addEventListener(type, fn) { (this.listeners[type] ||= new Set()).add(fn); } };
  const els = {
    "nav.langs": [nav],
    "nav.langs a[data-lang]": ["pl", "en", "uk"].map(link),
    "[data-i18n]": [{ dataset: { i18n: "src", i18nParamName: "src.psp" } }, { dataset: { i18n: "tab.map" } }],
    "[data-i18n-aria]": [{ dataset: { i18nAria: "nav.tabs" }, setAttribute(k, v) { this.attrs = { [k]: v }; } }],
  };
  const title = { dataset: { i18nTitle: "title.map" } };
  const d = doc || { documentElement: {}, title: "Alerty RCB — mapa alertów w Polsce",
    querySelector: (s) => (s === "title[data-i18n-title]" ? title : null),
    querySelectorAll: (s) => els[s] || [] };
  const store0 = { getItem: (k) => store[k] ?? null, setItem: (k, v) => { store[k] = v; } };
  const loc = { search };
  const RCB = new Function("document", "location", "localStorage", `${DICTS}\n${read("docs/common.js")}\n;return RCB;`)(d, loc, store0);
  return { RCB, d, els, store, loc, nav };
}
const text = (html, re) => [...html.matchAll(re)];
// the browser dispatches `type` on `target` inside the switcher
const fire = (nav, type, target) => { for (const fn of nav.listeners[type] || []) fn({ target }); };

test("the three dictionaries have the same keys and no empty text", () => {
  assert.deepEqual(Object.keys(i18n), CODES);
  const keys = Object.keys(i18n.pl).sort();
  assert.ok(keys.length > 40, `${keys.length} keys`);
  for (const c of CODES) {
    assert.deepEqual(Object.keys(i18n[c]).sort(), keys, c);
    for (const [k, v] of Object.entries(i18n[c])) assert.ok(typeof v === "string" && v.trim() && !/[{}]/.test(v.replace(/\{\w+\}/g, "")), `${c}.${k}`);
  }
  // a text has the same {placeholders} in every language
  const holes = (v) => [...new Set(text(v, /\{(\w+)\}/g).map((m) => m[1]))].sort();
  for (const k of keys) for (const c of CODES) assert.deepEqual(holes(i18n[c][k]), holes(i18n.pl[k]), `${c}.${k} placeholders`);
  // a count has all three forms
  for (const k of keys) if (/\.(one|few|many)$/.test(k)) for (const f of ["one", "few", "many"]) assert.ok(i18n.pl[k.replace(/\w+$/, f)] !== undefined, `${k}: no .${f}`);
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

// a marked element: data-i18n is its first attribute or a later one; its text is its own, with no child element
const MARKED = /<([a-z0-9]+)\s([^<>]*?)data-i18n="([^"]+)"([^<>]*)>([^<]+)<\/\1>/g;

test("the Polish dictionary says what each page says: every data-i18n mark is compared", () => {
  for (const f of PAGES) {
    const html = read("docs/" + f);
    const marks = text(html, /\sdata-i18n="([^"]+)"/g).map((m) => m[1]);
    const compared = text(html, MARKED).map((m) => m[3]);
    const missed = marks.filter((k) => !compared.includes(k));
    assert.equal(compared.length, marks.length, `${f}: ${marks.length} data-i18n marks, ${compared.length} compared; not compared: ${missed.join(", ") || "none"}`);
    for (const [, , before, key, after, txt] of text(html, MARKED)) {
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
    const i18nAt = html.indexOf('src="i18n.js" defer'), commonAt = html.indexOf('src="common.js" defer');
    assert.ok(i18nAt >= 0, `${f}: i18n.js is not loaded`);
    assert.ok(commonAt >= 0, `${f}: common.js is not loaded`);
    assert.ok(i18nAt < commonAt, `${f}: i18n.js must load before common.js`);
    for (const m of text(html, /src="(i18n-[\w-]+\.js)" defer/g)) {
      assert.ok(m.index > i18nAt && m.index < commonAt, `${f}: ${m[1]} must load between i18n.js and common.js`);
      assert.ok(read("docs/" + m[1]).includes("i18nAdd("), `${m[1]} adds its texts with i18nAdd()`);
    }
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

test("a switcher link followed after the page rewrote location.search carries the new parameters", () => {
  const { RCB, d, els, loc, nav } = load({ search: "?lang=uk&zoom=7" });
  RCB.applyI18n(d);
  assert.deepEqual(Object.keys(nav.listeners).sort(), ["auxclick", "click"]); // once at load and once here: added once
  assert.equal(nav.listeners.click.size, 1);
  const [pl, en, uk] = els["nav.langs a[data-lang]"];
  assert.equal(en.attrs.href, "?zoom=7&lang=en");
  // the visitor picks a period and moves the map (app.js: setPeriod, viewURL), so the URL is no longer the one at load
  const now = "?lang=uk&srodek=52.2297,21.0122&zoom=9&od=2026-11-01&do=2026-11-20&podklad=esri&zdjecie=2026-10-01";
  loc.search = now;
  const kept = "?srodek=52.2297,21.0122&zoom=9&od=2026-11-01&do=2026-11-20&podklad=esri&zdjecie=2026-10-01";
  fire(nav, "click", en); // the browser dispatches click, then follows the href
  assert.equal(en.attrs.href, kept + "&lang=en");
  fire(nav, "click", pl);
  assert.equal(pl.attrs.href, kept + "&lang=pl");
  fire(nav, "auxclick", uk); // the middle button
  assert.equal(uk.attrs.href, kept + "&lang=uk");
  fire(nav, "click", nav); // beside the links: nothing is followed and nothing changes
  assert.deepEqual([pl, en, uk].map((a) => a.attrs.href), [kept + "&lang=pl", kept + "&lang=en", kept + "&lang=uk"]);
});

test("without docs/i18n.js common.js still loads and t() gives the key back", () => {
  const RCB = new Function("document", `${read("docs/common.js")}\n;return RCB;`)({ querySelector: () => null });
  assert.equal(RCB.lang("", "en"), "en");
  assert.equal(RCB.t("tab.map", null, "en"), "tab.map");
  assert.equal(RCB.applyI18n({ querySelector: () => null }), "pl");
});

test("tn() picks the plural form of the language and fills {n}", () => {
  const { RCB } = load();
  for (const [n, pl, en, uk] of [[1, "one", "one", "one"], [3, "few", "many", "few"], [5, "many", "many", "many"], [22, "few", "many", "few"], [21, "many", "many", "one"]]) {
    for (const [c, f] of [["pl", pl], ["en", en], ["uk", uk]]) assert.equal(RCB.tn(n, "test.count", null, c), "test.count." + f, `${c} ${n}`);
  }
  assert.equal(RCB.loc("uk"), "uk-UA");
  assert.equal(RCB.loc("en"), "en-GB");
  assert.equal(RCB.loc("pl"), "pl-PL");
});

test("the shared helpers speak the page's language: categories, months, regions, durations", () => {
  const pl = load().RCB, en = load({ search: "?lang=en" }).RCB, uk = load({ store: { "alerty-lang": "uk" } }).RCB;
  assert.equal(pl.CAT.air, "Zagrożenie z powietrza");
  assert.equal(en.CAT.air, "Air threat");
  assert.equal(uk.CAT.air, "Загроза з повітря");
  assert.deepEqual([pl.MONTHS[10], en.MONTHS[10], uk.MONTHS[10]], ["listopad", "November", "листопад"]);
  assert.equal(pl.regionText(["mazowieckie"], [], ["Lesznowola"]), "woj. mazowieckie · gm. Lesznowola");
  assert.equal(en.regionText(["mazowieckie"], [], ["Lesznowola"]), "voiv. mazowieckie · comm. Lesznowola");
  assert.equal(uk.regionText(["mazowieckie"], ["1418"]), "воєв. mazowieckie · 1 пов.");
  assert.equal(uk.regionText([], []), "територію не вказано");
  const ago = (min) => new Date(Date.now() - min * 60000).toISOString();
  assert.equal(uk.duration(ago(5)), "5 хв");
  assert.equal(en.duration(ago(3 * 24 * 60)), "3 days");
  assert.equal(uk.duration(ago(5 * 24 * 60)), "5 днів");
  assert.equal(pl.duration(ago(2 * 24 * 60)), "2 dni");
});
