// Alerty RCB — the history page: every alert from data/archive.json, filtered and grouped by month.
"use strict";
const { CAT, VOIV, $, h, swatch, getJSON, fmtDay, fmtTime, fmtISO, hasTime, historyPeriod, inPeriod, regionText, t, tn } = RCB;
const PAGE = 150;
const LANG = RCB.lang();

// "Listopad 2026": the month by Intl in the interface language, standing alone, the first letter up
const MONTH = new Intl.DateTimeFormat(RCB.loc(), { month: "long", timeZone: "UTC" });
const monthName = (y, m) => { const n = MONTH.format(new Date(Date.UTC(y, m - 1, 15))); return n[0].toLocaleUpperCase(RCB.loc()) + n.slice(1); };

function row(a) {
  const d = new Date(a.started_at);
  const when = h("span", { class: "when mono" }, fmtDay(d), hasTime(a.started_at) ? h("br") : null, hasTime(a.started_at) ? fmtTime(d) : null);
  const msg = (a.message || a.title).replace(/^["„]|["”]$/g, "");
  return h("li", {},
    when,
    h("span", { class: "cat" }, swatch(a.category), CAT[a.category]),
    h("span", LANG === "pl" ? { class: "msg" } : { class: "msg", lang: "pl" }, msg, h("span", { class: "reg", text: regionText(a.voivodeships, a.powiaty, a.gminy) })),
    h("a", { class: "src", href: a.url, text: t("hist.link") }));
}

function render(rows, limit) {
  const list = $("#list");
  const shown = rows.slice(0, limit);
  const groups = new Map();
  for (const a of shown) {
    const key = a.date.slice(0, 7);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(a);
  }
  const perMonth = {};
  for (const a of rows) perMonth[a.date.slice(0, 7)] = (perMonth[a.date.slice(0, 7)] || 0) + 1;
  const parts = [...groups].map(([key, items]) => {
    const [y, m] = key.split("-").map(Number);
    return h("section", { class: "month" },
      h("h2", {}, `${monthName(y, m)} ${y}`, h("span", { class: "n", text: perMonth[key] })),
      h("ul", { class: "hist" }, ...items.map(row)));
  });
  if (!rows.length) parts.push(h("p", { class: "month muted", style: "padding:20px", text: t("hist.empty") }));
  if (rows.length > limit) {
    const btn = h("button", { class: "btn", type: "button", text: t("hist.more", { n: Math.min(PAGE, rows.length - limit) }) });
    btn.addEventListener("click", () => render(rows, limit + PAGE));
    parts.push(h("div", { class: "load-more" }, btn));
  }
  list.replaceChildren(...parts);
  $("#count").textContent = tn(rows.length, "hist.alerts");
}

async function main() {
  // Enter in a field must not send the form: the page's Content-Security-Policy forbids inline handlers, so
  // the rule lives here, before the first await, and holds when the archive fails to load too
  $("#filters").addEventListener("submit", (e) => e.preventDefault());
  RCB.strip();
  const desc = document.querySelector('meta[name="description"]');
  if (desc) desc.content = t("hist.desc");
  $("#q").placeholder = t("hist.qPh");
  if (LANG !== "pl") $("#orig").hidden = false; // the alert texts stay as RCB published them
  const [data] = await Promise.all([getJSON("data/archive.json"), RCB.names()]);
  const all = data.alerts.filter((a) => a.date >= "2020-01-01");
  const f = { cat: $("#f-cat"), voiv: $("#f-voiv"), year: $("#f-year"), q: $("#q") };
  const count = (pred) => all.filter(pred).length;
  for (const c of Object.keys(CAT)) f.cat.append(h("option", { value: c, text: `${CAT[c]} (${count((a) => a.category === c)})` }));
  for (const [id, name] of Object.entries(VOIV).sort((a, b) => a[1].localeCompare(b[1], "pl")))
    f.voiv.append(h("option", { value: id, text: name }));
  for (const y of [...new Set(all.map((a) => a.date.slice(0, 4)))].sort().reverse()) f.year.append(h("option", { value: y, text: y }));

  // filters live in the URL, so a filtered view can be shared
  const params = new URLSearchParams(location.search);
  for (const k of Object.keys(f)) if (params.get(k)) f[k].value = params.get(k);

  // a powiat filter, deep-linked from the analytics page: ?powiat=<województwo/powiat>.
  // It counts an alert that lists the powiat and one that covers its whole voivodeship,
  // like the map does. The name is resolved only when the filter is on.
  let powiat = params.get("powiat") || "";
  const chipName = h("span");
  const chipBtn = h("button", { type: "button", "aria-label": t("hist.rmPowiat"), text: "×" });
  const chip = h("span", { class: "chip", hidden: true }, chipName, chipBtn);
  chipBtn.addEventListener("click", () => { powiat = ""; chip.hidden = true; apply(); });
  const setChip = (name) => { chipName.textContent = name; chip.hidden = !powiat; };
  setChip(powiat || "");
  if (powiat) fetch("geo/poland.json").then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); }).then((geo) => {
    const p = geo.powiaty.find((x) => x.id === powiat);
    if (p) setChip(p.city ? p.name : t("hist.powiat", { name: p.name }));
  }).catch(() => {});
  $("#filters").append(chip);

  // a period, deep-linked from the map's «pełna historia» links: ?od=YYYY-MM-DD&do=YYYY-MM-DD, read as the
  // map reads it. A date that is not a real day leaves the archive unfiltered, as an unknown powiat does.
  let period = historyPeriod(location.search);
  const periodText = (per) => !per.to ? t("hist.from", { date: fmtISO(per.from) }) : per.from === per.to ? fmtISO(per.from) : `${fmtISO(per.from)} – ${fmtISO(per.to)}`;
  const periodBtn = h("button", { type: "button", "aria-label": t("hist.rmPeriod"), text: "×" });
  const periodChip = h("span", { class: "chip", hidden: true }, h("span", { text: period.from ? periodText(period) : "" }), periodBtn);
  periodBtn.addEventListener("click", () => { period = { from: null, to: null }; periodChip.hidden = true; apply(); });
  periodChip.hidden = !period.from;
  $("#filters").append(periodChip);

  const norm = (s) => s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/ł/g, "l");
  function apply() {
    const q = norm(f.q.value.trim());
    const rows = all.filter((a) =>
      inPeriod(a, period) &&
      (!f.cat.value || a.category === f.cat.value) &&
      (!f.voiv.value || a.voivodeships.includes(f.voiv.value)) &&
      (!f.year.value || a.date.startsWith(f.year.value)) &&
      (!powiat || a.powiaty.includes(powiat) || (a.whole || []).includes(powiat.split("/")[0])) &&
      (!q || norm(a.title + " " + a.message).includes(q)));
    const p = new URLSearchParams();
    for (const [k, e] of Object.entries(f)) if (e.value) p.set(k, e.value);
    if (powiat) p.set("powiat", powiat);
    if (period.from) { p.set("od", period.from); if (period.to) p.set("do", period.to); }
    if (params.get("lang")) p.set("lang", params.get("lang")); // the chosen language stays in the address
    history.replaceState(null, "", p.size ? "?" + p : location.pathname);
    render(rows, PAGE);
    if (powiat) $("#count").textContent += " · " + t("hist.wholeVoiv");
  }
  let timer;
  f.q.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(apply, 150); });
  for (const k of ["cat", "voiv", "year"]) f[k].addEventListener("change", apply);
  apply();
}

main().catch((e) => { $("#list").replaceChildren(h("p", { class: "month", text: t("hist.error", { msg: e.message }) })); });
