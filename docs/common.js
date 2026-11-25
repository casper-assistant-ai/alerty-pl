// Alerty RCB — shared by the map, the history and the analytics pages.
"use strict";

// The site is served over HTTPS only: the API's CORS allows only https origins, and push
// notifications need a secure context. Move plain-http visitors to https at once.
if (typeof location !== "undefined" && location.protocol === "http:" &&
    !/^(localhost|127\.0\.0\.1|\[::1\])$/.test(location.hostname)) {
  location.replace("https://" + location.host + location.pathname + location.search + location.hash);
}

const RCB = (() => {
  const CAT = {
    air: "Zagrożenie z powietrza", drill: "Ćwiczenia i testy syren", water: "Woda niezdatna do picia",
    weather: "Pogoda i powietrze", ordnance: "Niewybuchy i ewakuacje", fire: "Pożary",
    chemical: "Skażenia", other: "Inne komunikaty",
  };
  // map priority: when several alerts cover one powiat, the first category here wins
  const PRIORITY = ["air", "chemical", "fire", "ordnance", "weather", "water", "drill", "other"];
  const VOIV = {
    dolnoslaskie: "dolnośląskie", "kujawsko-pomorskie": "kujawsko-pomorskie", lubelskie: "lubelskie",
    lubuskie: "lubuskie", lodzkie: "łódzkie", malopolskie: "małopolskie", mazowieckie: "mazowieckie",
    opolskie: "opolskie", podkarpackie: "podkarpackie", podlaskie: "podlaskie", pomorskie: "pomorskie",
    slaskie: "śląskie", swietokrzyskie: "świętokrzyskie", "warminsko-mazurskie": "warmińsko-mazurskie",
    wielkopolskie: "wielkopolskie", zachodniopomorskie: "zachodniopomorskie",
  };
  const MONTHS = ["styczeń", "luty", "marzec", "kwiecień", "maj", "czerwiec", "lipiec", "sierpień",
    "wrzesień", "październik", "listopad", "grudzień"];

  // The live service (casper-infra deploy/alerty-api): polls gov.pl every 20 s and streams new alerts.
  // localStorage "alerty-api" overrides it for local testing.
  const API = (typeof localStorage !== "undefined" && localStorage.getItem("alerty-api")) ||
    "https://alerty-pl-cao.polandcentral.cloudapp.azure.com/alerty";
  const TEST = typeof location !== "undefined" && new URLSearchParams(location.search).has("test");

  const $ = (s, root = document) => root.querySelector(s);
  const color = (c) => `var(--${c})`;

  async function getJSON(url) {
    const r = await fetch(url + "?t=" + Math.floor(Date.now() / 60000), { cache: "no-store" });
    if (!r.ok) throw new Error(url + ": " + r.status);
    return r.json();
  }

  function h(tag, attrs = {}, ...kids) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "text") e.textContent = v;
      else if (k === "style") e.style.cssText = v;
      else e.setAttribute(k, v);
    }
    for (const k of kids) if (k != null) e.append(k);
    return e;
  }

  const swatch = (cat) => h("i", { class: "sw", style: `--c:${color(cat)}`, "aria-hidden": "true" });

  // Leaflet sits in the map pages' <script defer> row before this file, but one dropped request on a phone
  // leaves it unloaded and kills the page with "L is not defined". Wait for it, retrying the script once.
  function leaflet() {
    if (typeof L !== "undefined") return Promise.resolve(L);
    return new Promise((ok, bad) => {
      const miss = () => bad(new Error("biblioteka mapy (Leaflet) nie jest dostępna"));
      const s = document.createElement("script");
      s.src = "vendor/leaflet/leaflet.js";
      const late = setTimeout(() => { s.remove(); miss(); }, 15000);
      s.onload = () => { clearTimeout(late); ok(L); };
      s.onerror = () => { clearTimeout(late); s.remove(); miss(); };
      document.head.append(s);
    });
  }

  const pad = (n) => String(n).padStart(2, "0");
  const fmtDay = (d) => `${pad(d.getDate())}.${pad(d.getMonth() + 1)}.${d.getFullYear()}`;
  // "2026-11-07" -> "07.11.2026"
  const fmtISO = (iso) => iso.split("-").reverse().join(".");
  const fmtShort = (d) => `${pad(d.getDate())}.${pad(d.getMonth() + 1)} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  const fmtTime = (d) => `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  // a full ISO stamp -> "d.mm.yyyy, hh:mm" in Warsaw time, whatever the visitor's clock;
  // "" for anything new Date cannot read, so callers can fall back to the plain date
  const WARSAW = new Intl.DateTimeFormat("pl-PL", { timeZone: "Europe/Warsaw", day: "2-digit", month: "2-digit",
    year: "numeric", hour: "2-digit", minute: "2-digit" });
  const fmtStamp = (iso) => { const d = new Date(iso); return isNaN(d.getTime()) ? "" : WARSAW.format(d); };
  // an alert without an hour on gov.pl starts at 00:00: show the day only
  const hasTime = (iso) => !/T00:00:00/.test(iso);

  function duration(iso) {
    const min = Math.max(0, Math.round((Date.now() - new Date(iso)) / 60000));
    if (min < 60) return `${min} min`;
    const hrs = Math.floor(min / 60);
    return hrs < 48 ? `${hrs} h ${min % 60} min` : `${Math.floor(hrs / 24)} dni`;
  }

  // powiat id -> "pow. zgorzelecki" or "Wrocław" (geo/names.json); pages await names() before rendering
  let NAMES = {}, namesP = null;
  const names = () => namesP || (namesP = getJSON("geo/names.json").then((d) => { NAMES = d.powiaty || {}; })
    .catch(() => {}));

  // up to three items, then "i N inne"
  const few = (xs) => xs.length > 3 ? `${xs.slice(0, 3).join(", ")} i ${xs.length - 3} inne` : xs.join(", ");

  // "woj. dolnośląskie · pow. zgorzelecki · gm. Pieńsk"; a powiat with no known name is counted
  function regionText(voivodeships, powiaty, gminy = []) {
    if (!voivodeships.length) return "obszar nieustalony";
    const parts = ["woj. " + few(voivodeships.map((v) => VOIV[v] || v))];
    if (powiaty.length) {
      const known = powiaty.map((p) => NAMES[p]).filter(Boolean);
      parts.push(known.length === powiaty.length ? few(known) : `${powiaty.length} pow.`);
    }
    if (gminy && gminy.length) parts.push("gm. " + few(gminy));
    return parts.join(" · ");
  }

  // ---------- the period of the map page (shared with tests/period.test.mjs) ----------
  // a real calendar day written YYYY-MM-DD ("2026-02-31" and "2026-13-01" are not)
  const isISO = (v) => /^\d{4}-\d\d-\d\d$/.test(v || "") && !isNaN(Date.parse(v + "T12:00:00Z")) &&
    new Date(v + "T12:00:00Z").toISOString().slice(0, 10) === v;

  // ?od=…&do=… is a period, the old ?dzien=… one day, ?od= alone runs to today; anything else is today
  function periodFromQuery(search, today) {
    const q = new URLSearchParams(search);
    const to = isISO(q.get("do")) ? q.get("do") : isISO(q.get("dzien")) ? q.get("dzien") : today;
    const from = isISO(q.get("od")) ? q.get("od") : to;
    return { from, to };
  }

  // a period inside the archive [start, today]: swapped when backwards, cut at both ends
  function clampPeriod(from, to, start, today) {
    if (from > to) [from, to] = [to, from];
    if (from < start) from = start;
    if (to > today) to = today;
    if (to < start) to = start;
    if (from > today) from = today;
    if (from > to) from = to;
    return { from, to };
  }

  // ---------- the period of the history page ----------
  // ?od=…&do=… is read as the map reads it (one end alone: od runs on, do is that day), but with no "today"
  // to fall back on: no real date is the whole archive, and a backwards pair is swapped as the map shows it.
  function historyPeriod(search) {
    let { from, to } = periodFromQuery(search, null);
    if (from > to) [from, to] = [to, from];
    return { from, to };
  }

  // an archive row is in the period on its date, the day it was published; a missing end is open
  const inPeriod = (a, per) => (!per.from || a.date >= per.from) && (!per.to || a.date <= per.to);

  // the «pełna historia» links of the map page: a day or period the visitor chose is carried to the archive
  // page; today (its active alerts were published on other days, and the archive starts with today's rows)
  // and the whole archive open the plain page
  function historyLink(from, to, start, today) {
    const plain = (from === start && to === today) || (from === today && to === today);
    return plain ? "historia.html" : `historia.html?od=${from}&do=${to}`;
  }

  // an archived alert lasts from the day it started to the day of its last update (or today, while it is on)
  function span(a, today) {
    const start = a.started_at.slice(0, 10);
    let end = a.last_at && a.last_at.slice(0, 10) > start ? a.last_at.slice(0, 10) : start;
    if (a.status === "active" || a.status === "planned") end = today;
    return [start, end];
  }

  function plural(n, one, few, many) {
    const t = n % 10, tt = n % 100;
    if (n === 1) return one;
    return t >= 2 && t <= 4 && !(tt >= 12 && tt <= 14) ? few : many;
  }

  // live data first, the copy on GitHub Pages (Update data workflow) when the service does not answer
  async function liveData() {
    try {
      const r = await fetch(API + "/alerts", { cache: "no-store", signal: AbortSignal.timeout(6000) });
      if (r.ok) {
        const j = await r.json();
        if (j.meta && j.meta.checked_at && Array.isArray(j.alerts)) return [j, j.meta];
      }
    } catch (e) { /* fall back to Pages */ }
    return Promise.all([getJSON("data/alerts.json"), getJSON("data/meta.json")]);
  }

  // a new alert slides in at the bottom right and stays until closed
  function toast(d) {
    const a = d.alert;
    let box = $("#toasts");
    if (!box) { box = h("div", { id: "toasts", class: "toasts", "aria-live": "assertive" }); document.body.append(box); }
    const head = d.kind === "test" ? "Test powiadomień" : d.kind === "update" ? "Aktualizacja alertu" : "Nowy alert";
    const msg = (a.updates && a.updates[0] && a.updates[0].message) || a.intro || "";
    const close = h("button", { type: "button", class: "x", "aria-label": "Zamknij" }, "×");
    const t = h("div", { class: "toast", role: "alert", "data-alert": a.id },
      swatch(a.category), h("div", {}, h("strong", { text: head + ": " + (CAT[a.category] || CAT.other) }),
        h("p", { text: msg.slice(0, 280) }), h("a", { href: a.url, text: a.title })), close);
    close.addEventListener("click", () => t.remove());
    box.prepend(t);
  }

  // Server-Sent Events from the live service: each new or updated alert arrives within seconds.
  // Pages listen to the "rcb:alert" event on document; test alerts show only with ?test in the URL.
  function live() {
    if (!window.EventSource || live.es) return;
    const es = live.es = new EventSource(API + "/events");
    es.addEventListener("alert", (e) => {
      const d = JSON.parse(e.data);
      window.alertyLast = d;
      if (d.kind === "test" && !TEST) { console.info("alerty-pl: test alert", d.alert.id); return; }
      toast(d);
      strip();
      document.dispatchEvent(new CustomEvent("rcb:alert", { detail: d }));
    });
    es.addEventListener("ping", (e) => {
      const d = JSON.parse(e.data);
      const c = $("#strip .checked");
      if (c && d.checked_at) { c.textContent = "na żywo · sprawdzono " + fmtTime(new Date(d.checked_at)); $("#strip").classList.remove("stale"); }
    });
  }

  // the status strip under the header: the same on every page
  async function strip() {
    const el = $("#strip");
    if (!el) return null;
    try {
      const [data, meta] = await liveData();
      const active = data.alerts.filter((a) => a.status === "active" || a.status === "planned");
      const air = active.filter((a) => a.category === "air");
      const state = $(".state", el);
      let txt;
      if (air.length) {
        const vs = [...new Set(air.flatMap((a) => a.regions.voivodeships))];
        txt = "Zagrożenie z powietrza: " + (vs.length ? "woj. " + vs.map((v) => VOIV[v] || v).join(", ") : "obszar w komunikacie");
      } else {
        txt = "Brak zagrożenia z powietrza";
      }
      if (state.textContent !== txt) state.textContent = txt; // role=status announces only a real change
      $(".others", el).textContent = air.length
        ? (active.length > air.length ? `i ${active.length - air.length} inne alerty` : "")
        : (active.length ? `${active.length} ${plural(active.length, "inny alert", "inne alerty", "innych alertów")} w toku` : "inne alerty: brak");
      const checked = new Date(meta.checked_at);
      const stale = Date.now() - checked > 45 * 60000;
      $(".checked", el).textContent = (stale ? "dane nieaktualne, ostatnio " : meta.live ? "na żywo · sprawdzono " : "sprawdzono ")
        + (meta.live && !stale ? fmtTime(checked) : fmtShort(checked));
      el.classList.toggle("alarm", air.length > 0);
      el.classList.toggle("stale", stale);
      document.title = (air.length ? "Zagrożenie z powietrza — " : "") + document.title.replace(/^Zagrożenie z powietrza — /, "");
      return { data, meta, active };
    } catch (e) {
      $(".state", el).textContent = "Nie udało się pobrać danych";
      $(".checked", el).textContent = e.message;
      el.classList.add("stale");
      return null;
    }
  }

  // the footer shows the site's version from the changelog
  const ver = $("#ver");
  if (ver) getJSON("data/changelog.json").then((d) => {
    const r = d.releases.find((x) => x.version);
    if (r) ver.textContent = "wersja " + r.version + " · historia zmian";
  }).catch(() => {});

  if ($("#strip")) live();

  // ---------- interface language (docs/i18n.js: the shared chrome in PL / EN / UK) ----------
  // ?lang=pl|en|uk wins, then the choice kept in localStorage (one key on every page), then pl; an unknown code is ignored
  const LANGS = ["pl", "en", "uk"], LANG_KEY = "alerty-lang";
  const storedLang = () => { try { return typeof localStorage === "undefined" ? null : localStorage.getItem(LANG_KEY); } catch (e) { return null; } };
  function lang(search, stored) {
    if (search === undefined) search = typeof location !== "undefined" ? location.search : "";
    const q = new URLSearchParams(search).get("lang");
    if (LANGS.includes(q)) return q;
    if (stored === undefined) stored = storedLang();
    return LANGS.includes(stored) ? stored : "pl";
  }
  // t("src", { name: "gov.pl" }) -> "źródło: gov.pl"; a text missing in the chosen language comes from Polish
  function t(key, params, code = lang()) {
    const dict = (typeof I18N === "undefined" ? null : I18N) || {};
    let s = (dict[code] && dict[code][key]) || (dict.pl && dict.pl[key]) || key;
    for (const [k, v] of Object.entries(params || {})) s = s.split("{" + k + "}").join(v);
    return s;
  }
  // the link of a switcher entry: every other URL parameter byte for byte, and lang set to that language
  function langUrl(search, code) {
    const parts = (search || "").replace(/^\?/, "").split("&").filter((p) => p && p.split("=")[0] !== "lang");
    return "?" + parts.concat("lang=" + code).join("&");
  }
  // the pages rewrite their URL after load (the period, the view, the place: history.replaceState fires no event), so
  // the href set on DOM ready goes stale: when a switcher link is followed, point it at the URL of the moment again
  function langClick(e) {
    const el = e && e.target;
    const a = el && typeof el.closest === "function" ? el.closest("a[data-lang]") : null;
    if (a) a.setAttribute("href", langUrl(typeof location !== "undefined" ? location.search : "", a.dataset.lang));
  }
  // on DOM ready: the links of the switcher (the current one aria-current) and the click handler that keeps them
  // current; in another language also <html lang>, <title> and the text or aria-label of every [data-i18n] element.
  // A page that chose no language stays as it is.
  function applyI18n(doc = document) {
    if (typeof doc.querySelectorAll !== "function") return "pl";
    const search = typeof location !== "undefined" ? location.search : "";
    const code = lang(search);
    if (new URLSearchParams(search).get("lang") === code) { // the URL's choice becomes the kept one
      try { if (typeof localStorage !== "undefined") localStorage.setItem(LANG_KEY, code); } catch (e) { /* private mode */ }
    }
    for (const a of doc.querySelectorAll("nav.langs a[data-lang]")) {
      a.setAttribute("href", langUrl(search, a.dataset.lang));
      if (a.dataset.lang === code) a.setAttribute("aria-current", "true"); else a.removeAttribute("aria-current");
    }
    // click (also Enter and Ctrl+click) and auxclick (the middle button): the same listener twice is added once
    for (const nav of doc.querySelectorAll("nav.langs")) {
      if (typeof nav.addEventListener === "function") for (const type of ["click", "auxclick"]) nav.addEventListener(type, langClick);
    }
    if (code === "pl") return code;
    doc.documentElement.lang = code;
    const title = doc.querySelector("title[data-i18n-title]");
    if (title) doc.title = t(title.dataset.i18nTitle, null, code);
    for (const el of doc.querySelectorAll("[data-i18n]")) {
      const params = {};
      // data-i18n-param-name="src.gov" fills {name} with that key's text
      for (const [k, v] of Object.entries(el.dataset)) if (k.startsWith("i18nParam")) params[k.slice(9, 10).toLowerCase() + k.slice(10)] = t(v, null, code);
      el.textContent = t(el.dataset.i18n, params, code);
    }
    for (const el of doc.querySelectorAll("[data-i18n-aria]")) el.setAttribute("aria-label", t(el.dataset.i18nAria, null, code));
    return code;
  }

  return { isISO, periodFromQuery, clampPeriod, span, historyPeriod, inPeriod, historyLink, API, CAT, PRIORITY, VOIV, MONTHS, $, h, color, swatch, leaflet, getJSON,
    fmtISO, fmtDay, fmtShort, fmtTime, fmtStamp,
    hasTime, duration, regionText, names, plural, strip, live, LANGS, lang, t, langUrl, applyI18n };
})();

// docs/i18n.js (loaded before this file) brings the dictionaries; without them nothing is translated.
(() => {
  if (typeof document === "undefined" || typeof I18N === "undefined" || typeof document.querySelectorAll !== "function") return;
  const go = () => RCB.applyI18n();
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", go); else go();
})();

// The tab row scrolls sideways on a narrow phone (six tabs): show the current tab and fade the side with more tabs.
(() => {
  if (typeof document === "undefined") return;
  const go = () => {
    const nav = document.querySelector("nav.tabs");
    if (!nav) return;
    const flag = () => {
      const more = [];
      if (nav.scrollLeft > 2) more.push("l");
      if (nav.scrollLeft + nav.clientWidth < nav.scrollWidth - 2) more.push("r");
      if (more.length) nav.dataset.more = more.join(" "); else delete nav.dataset.more;
    };
    const cur = nav.querySelector('[aria-current="page"]');
    if (cur && nav.scrollWidth > nav.clientWidth) nav.scrollLeft = cur.offsetLeft - nav.offsetLeft - (nav.clientWidth - cur.offsetWidth) / 2;
    flag();
    nav.addEventListener("scroll", flag, { passive: true });
    addEventListener("resize", flag);
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", go); else go();
})();
