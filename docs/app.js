// Alerty RCB — the map page: draws geo/poland.json and colours powiaty from data/alerts.json.
"use strict";
const { CAT, PRIORITY, $, h, color, swatch, getJSON, fmtShort, fmtDay, hasTime, duration, regionText } = RCB;
const NS = "http://www.w3.org/2000/svg";

function el(tag, attrs = {}, parent) {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (parent) parent.appendChild(e);
  return e;
}

function drawMap(geo) {
  const svg = $("#map");
  svg.setAttribute("viewBox", `0 0 ${geo.width} ${geo.height}`);
  const gp = el("g", {}, svg), gw = el("g", {}, svg), gt = el("g", {}, svg);
  for (const p of geo.powiaty) {
    const path = el("path", { d: p.d, class: "pow", "data-id": p.id, "data-v": p.voivodeship }, gp);
    path.dataset.name = (p.city ? "" : "powiat ") + p.name;
  }
  for (const v of geo.voivodeships) {
    el("path", { d: v.d, class: "woj" }, gw);
    el("text", { x: v.cx, y: v.cy }, gt).textContent = v.name;
  }
}

const covers = (a, p) => a.regions.powiaty.includes(p.dataset.id) || a.regions.whole.includes(p.dataset.v);

function paint(geo, alerts) {
  const fill = {};
  const put = (id, cat) => {
    if (!fill[id] || PRIORITY.indexOf(cat) < PRIORITY.indexOf(fill[id])) fill[id] = cat;
  };
  for (const a of alerts) {
    for (const p of a.regions.powiaty) put(p, a.category);
    for (const v of a.regions.whole) geo.powiaty.filter((p) => p.voivodeship === v).forEach((p) => put(p.id, a.category));
  }
  document.querySelectorAll("#map path.pow").forEach((p) => {
    const cat = fill[p.dataset.id];
    p.style.fill = cat ? color(cat) : "";
    p.classList.toggle("hit", !!cat);
    p.classList.toggle("blink", cat === "air");
  });
  const used = new Set(Object.values(fill));
  // the legend shows what is on the map now; with nothing active it explains the colours anyway
  const cats = used.size ? PRIORITY.filter((c) => used.has(c)) : ["air", "water", "weather", "drill"];
  $("#legend").replaceChildren(...cats.map((c) => h("li", {}, swatch(c), CAT[c])));
}

function tooltips(state) {
  const tip = $("#tip"), wrap = $(".map-wrap");
  $("#map").addEventListener("pointermove", (e) => {
    const p = e.target.closest("path.pow");
    if (!p) { tip.hidden = true; return; }
    const hits = state.active.filter((a) => covers(a, p));
    tip.replaceChildren(h("b", { text: p.dataset.name }),
      h("div", { text: hits.length ? hits.map((a) => CAT[a.category]).join(", ") : "brak alertów" }));
    const r = wrap.getBoundingClientRect();
    const x = Math.min(e.clientX - r.left + 12, r.width - 200);
    tip.style.left = x + "px";
    tip.style.top = e.clientY - r.top + 12 + "px";
    tip.hidden = false;
  });
  $("#map").addEventListener("pointerleave", () => (tip.hidden = true));
}

function activeRow(a) {
  const msg = (a.updates[0] && a.updates[0].message) || a.intro;
  const link = h("a", { href: a.url, text: "komunikat" });
  const since = a.status === "planned" ? "planowany od " + fmtShort(new Date(a.started_at)) : "trwa " + duration(a.started_at);
  return h("li", {},
    h("div", { class: "row-head" }, swatch(a.category), CAT[a.category]),
    h("p", { class: "row-msg", text: msg.replace(/^"|"$/g, "") }),
    h("div", { class: "row-meta mono" }, h("span", { text: regionText(a.regions.voivodeships, a.regions.powiaty) }), h("span", { text: since }), link));
}

function recentRow(a) {
  const d = new Date(a.started_at);
  return h("li", {},
    h("span", { class: "when mono", text: hasTime(a.started_at) ? fmtShort(d) : fmtDay(d).slice(0, 5) }),
    h("a", { class: "what", href: a.url }, swatch(a.category), h("span", { text: `${CAT[a.category]} · ${regionText(a.regions.voivodeships, [])}` })));
}

async function main() {
  const geo = await getJSON("geo/poland.json");
  drawMap(geo);
  const state = { active: [] };
  tooltips(state);
  async function refresh() {
    const res = await RCB.strip();
    if (!res) return;
    const { data, active } = res;
    state.active = active;
    paint(geo, active);
    const cutoff = Date.now() - 7 * 86400000;
    const recent = data.alerts.filter((a) => !active.includes(a) && new Date(a.last_at) > cutoff && a.category !== "other");
    $("#active-count").textContent = active.length;
    $("#active").replaceChildren(...(active.length ? active.map(activeRow)
      : [h("li", { class: "empty", text: "Żaden alert RCB nie jest teraz aktywny." })]));
    $("#week-count").textContent = recent.length;
    $("#recent").replaceChildren(...(recent.length ? recent.slice(0, 12).map(recentRow)
      : [h("li", { class: "empty", text: "W tym tygodniu nie było alertów." })]));
  }
  await refresh();
  setInterval(refresh, 60000);
}

main();
