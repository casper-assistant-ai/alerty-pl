// Alerty RCB — shared by the map, the history and the analytics pages.
"use strict";

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

  const pad = (n) => String(n).padStart(2, "0");
  const fmtDay = (d) => `${pad(d.getDate())}.${pad(d.getMonth() + 1)}.${d.getFullYear()}`;
  const fmtShort = (d) => `${pad(d.getDate())}.${pad(d.getMonth() + 1)} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  const fmtTime = (d) => `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  // an alert without an hour on gov.pl starts at 00:00: show the day only
  const hasTime = (iso) => !/T00:00:00/.test(iso);

  function duration(iso) {
    const min = Math.max(0, Math.round((Date.now() - new Date(iso)) / 60000));
    if (min < 60) return `${min} min`;
    const hrs = Math.floor(min / 60);
    return hrs < 48 ? `${hrs} h ${min % 60} min` : `${Math.floor(hrs / 24)} dni`;
  }

  function regionText(voivodeships, powiaty) {
    if (!voivodeships.length) return "obszar nieustalony";
    const vs = voivodeships.map((v) => VOIV[v] || v);
    const head = vs.length > 3 ? `${vs.slice(0, 3).join(", ")} i ${vs.length - 3} inne` : vs.join(", ");
    return "woj. " + head + (powiaty.length ? ` · ${powiaty.length} pow.` : "");
  }

  function plural(n, one, few, many) {
    const t = n % 10, tt = n % 100;
    if (n === 1) return one;
    return t >= 2 && t <= 4 && !(tt >= 12 && tt <= 14) ? few : many;
  }

  // the status strip under the header: the same on every page
  async function strip() {
    const el = $("#strip");
    if (!el) return null;
    try {
      const [data, meta] = await Promise.all([getJSON("data/alerts.json"), getJSON("data/meta.json")]);
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
      const stale = Date.now() - checked > 30 * 60000;
      $(".checked", el).textContent = (stale ? "dane nieaktualne, ostatnio " : "sprawdzono ") + fmtShort(checked);
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

  return { CAT, PRIORITY, VOIV, MONTHS, $, h, color, swatch, getJSON, fmtDay, fmtShort, fmtTime, hasTime,
    duration, regionText, plural, strip };
})();
