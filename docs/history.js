// Alerty RCB — the history page: every alert from data/archive.json, filtered and grouped by month.
"use strict";
const { CAT, VOIV, MONTHS, $, h, swatch, getJSON, fmtDay, fmtTime, hasTime, regionText, plural } = RCB;
const PAGE = 150;

function row(a) {
  const d = new Date(a.started_at);
  const when = h("span", { class: "when mono" }, fmtDay(d), hasTime(a.started_at) ? h("br") : null, hasTime(a.started_at) ? fmtTime(d) : null);
  const msg = (a.message || a.title).replace(/^["„]|["”]$/g, "");
  return h("li", {},
    when,
    h("span", { class: "cat" }, swatch(a.category), CAT[a.category]),
    h("span", { class: "msg" }, msg, h("span", { class: "reg", text: regionText(a.voivodeships, a.powiaty) })),
    h("a", { class: "src", href: a.url, text: "komunikat" }));
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
      h("h2", {}, `${MONTHS[m - 1][0].toUpperCase()}${MONTHS[m - 1].slice(1)} ${y}`, h("span", { class: "n", text: perMonth[key] })),
      h("ul", { class: "hist" }, ...items.map(row)));
  });
  if (!rows.length) parts.push(h("p", { class: "month muted", style: "padding:20px", text: "Brak alertów dla tych filtrów." }));
  if (rows.length > limit) {
    const btn = h("button", { class: "btn", type: "button", text: `Pokaż kolejne ${Math.min(PAGE, rows.length - limit)}` });
    btn.addEventListener("click", () => render(rows, limit + PAGE));
    parts.push(h("div", { class: "load-more" }, btn));
  }
  list.replaceChildren(...parts);
  $("#count").textContent = `${rows.length} ${plural(rows.length, "alert", "alerty", "alertów")}`;
}

async function main() {
  RCB.strip();
  const data = await getJSON("data/archive.json");
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
  const chipBtn = h("button", { type: "button", "aria-label": "Usuń filtr powiatu", text: "×" });
  const chip = h("span", { class: "chip", hidden: true }, chipName, chipBtn);
  chipBtn.addEventListener("click", () => { powiat = ""; chip.hidden = true; apply(); });
  const setChip = (name) => { chipName.textContent = name; chip.hidden = !powiat; };
  setChip(powiat || "");
  if (powiat) fetch("geo/poland.json").then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); }).then((geo) => {
    const p = geo.powiaty.find((x) => x.id === powiat);
    if (p) setChip((p.city ? "" : "pow. ") + p.name);
  }).catch(() => {});
  $("#filters").append(chip);

  const norm = (s) => s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/ł/g, "l");
  function apply() {
    const q = norm(f.q.value.trim());
    const rows = all.filter((a) =>
      (!f.cat.value || a.category === f.cat.value) &&
      (!f.voiv.value || a.voivodeships.includes(f.voiv.value)) &&
      (!f.year.value || a.date.startsWith(f.year.value)) &&
      (!powiat || a.powiaty.includes(powiat) || (a.whole || []).includes(powiat.split("/")[0])) &&
      (!q || norm(a.title + " " + a.message).includes(q)));
    const p = new URLSearchParams();
    for (const [k, e] of Object.entries(f)) if (e.value) p.set(k, e.value);
    if (powiat) p.set("powiat", powiat);
    history.replaceState(null, "", p.size ? "?" + p : location.pathname);
    render(rows, PAGE);
    if (powiat) $("#count").textContent += " · w tym alerty dla całego województwa";
  }
  let t;
  f.q.addEventListener("input", () => { clearTimeout(t); t = setTimeout(apply, 150); });
  for (const k of ["cat", "voiv", "year"]) f[k].addEventListener("change", apply);
  apply();
}

main().catch((e) => { $("#list").replaceChildren(h("p", { class: "month", text: "Nie udało się wczytać archiwum: " + e.message })); });
