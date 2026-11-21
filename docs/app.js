// Alerty RCB — draws the map from geo/poland.json and colours it from data/alerts.json.
const CAT = {
  air: "Zagrożenie z powietrza", drill: "Ćwiczenia / test syren", water: "Woda niezdatna do picia",
  weather: "Pogoda / powietrze", ordnance: "Niewybuch / ewakuacja", fire: "Pożar",
  chemical: "Skażenie", other: "Inne komunikaty",
};
const PRIORITY = ["air", "chemical", "fire", "ordnance", "weather", "water", "drill", "other"];
const NS = "http://www.w3.org/2000/svg";
const $ = (s) => document.querySelector(s);
const color = (c) => getComputedStyle(document.documentElement).getPropertyValue("--" + c).trim();

async function getJSON(url) {
  const r = await fetch(url + "?t=" + Math.floor(Date.now() / 60000), { cache: "no-store" });
  if (!r.ok) throw new Error(url + ": " + r.status);
  return r.json();
}

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
    el("path", { d: v.d, class: "woj", "data-id": v.id }, gw);
    const t = el("text", { x: v.cx, y: v.cy }, gt);
    t.textContent = v.name;
  }
}

function fmtTime(iso) {
  const d = new Date(iso);
  return d.toLocaleString("pl-PL", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function duration(iso) {
  const min = Math.max(0, Math.round((Date.now() - new Date(iso)) / 60000));
  return min < 60 ? `${min} min` : `${Math.floor(min / 60)} h ${min % 60} min`;
}

function regionLine(a, geo) {
  const vn = Object.fromEntries(geo.voivodeships.map((v) => [v.id, v.name]));
  const vs = a.regions.voivodeships.map((v) => "woj. " + (vn[v] || v));
  const n = a.regions.powiaty.length;
  return vs.join(", ") + (n ? ` · ${n} pow.` : "");
}

function item(a, geo, live) {
  const li = document.createElement("li");
  li.style.setProperty("--c", color(a.category));
  const msg = (a.updates[0] && a.updates[0].message) || a.intro;
  li.innerHTML = `<div class="t"></div><div class="m"></div><div class="r"></div><div class="when"></div>`;
  li.querySelector(".t").textContent = CAT[a.category] + (a.status === "planned" ? " (planowane)" : "");
  li.querySelector(".m").textContent = msg;
  li.querySelector(".r").textContent = regionLine(a, geo);
  const w = li.querySelector(".when");
  w.innerHTML = live ? `trwa ${duration(a.started_at)} · ` : `${fmtTime(a.last_at > a.started_at ? a.last_at : a.started_at)} · `;
  const link = document.createElement("a");
  link.href = a.url; link.textContent = "komunikat RCB";
  w.appendChild(link);
  return li;
}

function paint(geo, alerts) {
  const fill = {}; // powiat id -> category (highest priority)
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
    p.dataset.cat = cat || "";
  });
}

function tooltips(alerts) {
  const tip = $("#tip"), wrap = $(".map-wrap");
  $("#map").addEventListener("mousemove", (e) => {
    const p = e.target.closest("path.pow");
    if (!p) { tip.hidden = true; return; }
    const hits = alerts.filter((a) => a.regions.powiaty.includes(p.dataset.id) || a.regions.whole.includes(p.dataset.v));
    tip.innerHTML = "";
    const b = document.createElement("b"); b.textContent = p.dataset.name; tip.appendChild(b);
    const s = document.createElement("div");
    s.textContent = hits.length ? hits.map((a) => CAT[a.category]).join(", ") : "brak alertów";
    tip.appendChild(s);
    const r = wrap.getBoundingClientRect();
    tip.style.left = e.clientX - r.left + 14 + "px";
    tip.style.top = e.clientY - r.top + 14 + "px";
    tip.hidden = false;
  });
  $("#map").addEventListener("mouseleave", () => (tip.hidden = true));
}

function legend() {
  $("#legend").innerHTML = PRIORITY.filter((c) => c !== "other")
    .map((c) => `<span><i style="background:${color(c)}"></i>${CAT[c]}</span>`).join("");
}

async function main() {
  const geo = await getJSON("geo/poland.json");
  drawMap(geo);
  legend();
  let bound = false;
  async function refresh() {
    try {
      const [data, meta] = await Promise.all([getJSON("data/alerts.json"), getJSON("data/meta.json")]);
      const active = data.alerts.filter((a) => a.status === "active" || a.status === "planned");
      const cutoff = Date.now() - 14 * 86400000;
      const recent = data.alerts.filter((a) => !active.includes(a) && new Date(a.last_at) > cutoff && a.category !== "other");
      paint(geo, active);
      if (!bound) { tooltips(active); bound = true; }
      const ul = $("#active"); ul.innerHTML = "";
      if (!active.length) {
        const li = document.createElement("li"); li.className = "empty"; li.textContent = "Brak aktywnych alertów RCB."; ul.appendChild(li);
      }
      active.forEach((a) => ul.appendChild(item(a, geo, true)));
      const ur = $("#recent"); ur.innerHTML = "";
      recent.slice(0, 30).forEach((a) => ur.appendChild(item(a, geo, false)));
      const n = active.length, air = active.some((a) => a.category === "air");
      $("#active-count").textContent = n;
      $("#active-count").classList.toggle("zero", !n);
      const st = $("#status");
      st.textContent = (air ? "⚠ Zagrożenie z powietrza · " : "") + "sprawdzono " + fmtTime(meta.checked_at);
      st.classList.toggle("alarm", air);
      document.title = (air ? "⚠ " : "") + "Alerty RCB — mapa alertów w Polsce";
    } catch (e) {
      $("#status").textContent = "Nie udało się pobrać danych: " + e.message;
    }
  }
  await refresh();
  setInterval(refresh, 60000);
}

main();
