// Alerty RCB — the analytics page: counts from data/archive.json over a chosen period.
"use strict";
const { CAT, VOIV, MONTHS, $, h, swatch, getJSON, fmtDay, plural } = RCB;
const NS = "http://www.w3.org/2000/svg";
const DAY = 86400000;

function s(tag, attrs = {}, parent, text) {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (text != null) e.textContent = text;
  if (parent) parent.appendChild(e);
  return e;
}

const fmtN = (n) => n.toLocaleString("pl-PL");
const startOfDay = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
const monday = (d) => { const x = startOfDay(d); x.setDate(x.getDate() - ((x.getDay() + 6) % 7)); return x; };

function inPeriod(all, period, now) {
  if (period === "all") return { rows: all, from: new Date(all[all.length - 1].started_at), prev: null };
  const from = new Date(now - period * DAY);
  const prevFrom = new Date(now - 2 * period * DAY);
  return {
    rows: all.filter((a) => new Date(a.started_at) >= from),
    prev: all.filter((a) => { const d = new Date(a.started_at); return d >= prevFrom && d < from; }),
    from,
  };
}

function delta(n, prev, period) {
  if (prev == null) return "";
  const d = n - prev;
  const span = period === 90 ? "poprzednie 90 dni" : "poprzednie 12 mies.";
  return `${d > 0 ? "+" : d < 0 ? "−" : "±"}${Math.abs(d)} wobec ${prev} za ${span}`;
}

function stats(cur, period, now) {
  const air = cur.rows.filter((a) => a.category === "air");
  const prevAir = cur.prev && cur.prev.filter((a) => a.category === "air");
  const byV = countVoiv(cur.rows);
  const top = Object.entries(byV).sort((a, b) => b[1] - a[1])[0];
  const days = new Set(cur.rows.map((a) => a.date)).size;
  const spanDays = Math.max(1, Math.round((now - cur.from) / DAY));
  const lastAir = air[0];
  const card = (label, value, sub) => h("div", { class: "stat" },
    h("div", { class: "label", text: label }), h("div", { class: "value", text: value }), h("div", { class: "delta mono", text: sub }));
  $("#stats").replaceChildren(
    card("Wszystkie alerty", fmtN(cur.rows.length), delta(cur.rows.length, cur.prev && cur.prev.length, period) || `od ${fmtDay(cur.from)}`),
    card("Zagrożenie z powietrza", fmtN(air.length), delta(air.length, prevAir && prevAir.length, period) || (lastAir ? `ostatnio ${fmtDay(new Date(lastAir.started_at))}` : "")),
    card("Dni z alertem", fmtN(days), `z ${fmtN(spanDays)} ${plural(spanDays, "dnia", "dni", "dni")} w okresie`),
    card("Najwięcej alertów", top ? VOIV[top[0]] : "—", top ? `${fmtN(top[1])} ${plural(top[1], "alert", "alerty", "alertów")} w województwie` : ""));
}

function countVoiv(rows) {
  const c = {};
  for (const a of rows) for (const v of a.voivodeships) c[v] = (c[v] || 0) + 1;
  return c;
}

// main chart: stacked bars, air threats in the accent, everything else in one neutral
function timeChart(cur, period, now) {
  const svg = $("#c-time");
  const W = Math.max(320, svg.parentElement.clientWidth - 48), H = W < 600 ? 200 : 260;
  const unit = period === 90 ? "day" : period === 365 ? "week" : "month";
  const keyOf = (d) => unit === "day" ? startOfDay(d).getTime() : unit === "week" ? monday(d).getTime() : new Date(d.getFullYear(), d.getMonth(), 1).getTime();
  const bins = [];
  let t = new Date(keyOf(cur.from));
  while (t <= now) {
    bins.push({ k: t.getTime(), d: new Date(t), air: 0, rest: 0 });
    t = unit === "day" ? new Date(t.getFullYear(), t.getMonth(), t.getDate() + 1)
      : unit === "week" ? new Date(t.getFullYear(), t.getMonth(), t.getDate() + 7)
      : new Date(t.getFullYear(), t.getMonth() + 1, 1);
  }
  const idx = new Map(bins.map((b, i) => [b.k, i]));
  for (const a of cur.rows) {
    const i = idx.get(keyOf(new Date(a.started_at)));
    if (i == null) continue;
    bins[i][a.category === "air" ? "air" : "rest"]++;
  }
  const max = Math.max(1, ...bins.map((b) => b.air + b.rest));
  const step = max <= 5 ? 1 : max <= 12 ? 2 : max <= 30 ? 5 : max <= 60 ? 10 : 20;
  const top = Math.ceil(max / step) * step;
  const L = 32, R = 8, T = 8, B = 28, iw = W - L - R, ih = H - T - B;
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.replaceChildren();
  const grid = s("g", { class: "grid" }, svg), axis = s("g", { class: "axis" }, svg), bars = s("g", {}, svg), hov = s("g", {}, svg);
  for (let v = 0; v <= top; v += step) {
    const y = T + ih - (v / top) * ih;
    s("line", { x1: L, x2: W - R, y1: y, y2: y }, grid);
    s("text", { x: L - 8, y: y + 4, "text-anchor": "end" }, axis, v);
  }
  const bw = iw / bins.length, gap = bins.length > 120 ? 0.5 : Math.min(4, bw * 0.25);
  const label = (b) => unit === "day" ? fmtDay(b.d) : unit === "week" ? `tydzień od ${fmtDay(b.d)}` : `${MONTHS[b.d.getMonth()]} ${b.d.getFullYear()}`;
  bins.forEach((b, i) => {
    const x = L + i * bw + gap / 2, w = Math.max(1, bw - gap);
    const hr = (b.rest / top) * ih, ha = (b.air / top) * ih;
    if (b.rest) s("rect", { class: "b-rest", x, width: w, y: T + ih - hr, height: hr, rx: Math.min(2, w / 2) }, bars);
    if (b.air) s("rect", { class: "b-air", x, width: w, y: T + ih - hr - ha, height: ha, rx: Math.min(2, w / 2) }, bars);
    const r = s("rect", { class: "hov", x: L + i * bw, width: bw, y: T, height: ih }, hov);
    s("title", {}, r, `${label(b)}: ${b.air + b.rest} ${plural(b.air + b.rest, "alert", "alerty", "alertów")}${b.air ? `, z powietrza ${b.air}` : ""}`);
  });
  // x labels: months (or years for the whole archive), never more than about one per 64 px
  let lastLabel = -Infinity;
  bins.forEach((b, i) => {
    const d = b.d;
    const first = unit === "month" ? d.getMonth() === 0 : unit === "week" ? d.getDate() <= 7 : d.getDate() === 1;
    const x = L + i * bw;
    if (!first || x - lastLabel < 64) return;
    lastLabel = x;
    s("line", { x1: x, x2: x, y1: T + ih, y2: T + ih + 4, stroke: "currentColor", opacity: .3 }, axis);
    s("text", { x: x + 2, y: H - 8 }, axis, unit === "month" ? d.getFullYear() : `${MONTHS[d.getMonth()].slice(0, 3)}${d.getMonth() === 0 ? " " + d.getFullYear() : ""}`);
  });
  const per = unit === "day" ? "dziennie" : unit === "week" ? "tygodniowo" : "miesięcznie";
  $("#time-sub").textContent = `Liczba alertów ${per}, od ${fmtDay(cur.from)} do dziś`;
}

function heatMap(geo, byV) {
  const svg = $("#c-map");
  if (!svg.dataset.drawn) {
    svg.setAttribute("viewBox", `0 0 ${geo.width} ${geo.height}`);
    const g = s("g", {}, svg), gt = s("g", {}, svg);
    for (const v of geo.voivodeships) {
      s("path", { d: v.d, class: "heat", "data-id": v.id, stroke: "var(--surface)", "stroke-width": 2 }, g);
      s("text", { x: v.cx, y: v.cy + 8, "data-id": v.id, class: "heat-n" }, gt);
    }
    svg.dataset.drawn = "1";
  }
  const vals = geo.voivodeships.map((v) => byV[v.id] || 0);
  const max = Math.max(1, ...vals), min = Math.min(...vals);
  const shade = (n) => `color-mix(in oklab, var(--land), var(--accent) ${Math.round(6 + 84 * ((n - min) / Math.max(1, max - min)))}%)`;
  svg.querySelectorAll("path.heat").forEach((p) => {
    const n = byV[p.dataset.id] || 0;
    p.style.fill = n ? shade(n) : "var(--land)";
    p.replaceChildren(s("title", {}, null, `${VOIV[p.dataset.id]}: ${n}`));
  });
  svg.querySelectorAll("text").forEach((t) => {
    const n = byV[t.dataset.id] || 0;
    t.textContent = n;
    const dark = (n - min) / Math.max(1, max - min) > 0.5;
    t.style.stroke = dark ? "transparent" : "";
    t.style.fill = dark ? "#fff" : "";
  });
  $("#ramp").style.background = `linear-gradient(90deg, ${shade(min)}, ${shade(max)})`;
  $("#ramp-min").textContent = min;
  $("#ramp-max").textContent = max;
}

function ranked(ul, items, fmt) {
  const max = Math.max(1, ...items.map((i) => i.n));
  ul.replaceChildren(...items.map((i) => h("li", {},
    h("span", { class: "name" }, i.cat ? swatch(i.cat) : null, h("span", { text: fmt(i) })),
    h("span", { class: "num", text: fmtN(i.n) }),
    h("span", { class: "track", "aria-hidden": "true" }, h("i", { style: `width:${(100 * i.n / max).toFixed(1)}%${i.cat ? `;--c:var(--${i.cat})` : ""}` })))));
  if (!items.length) ul.replaceChildren(h("li", { class: "muted", text: "Brak danych w tym okresie" }));
}

function hourChart(cur) {
  const svg = $("#c-hour");
  const W = Math.max(320, svg.parentElement.clientWidth - 48), H = 160;
  const bins = Array.from({ length: 24 }, () => ({ air: 0, rest: 0 }));
  let n = 0;
  for (const a of cur.rows) {
    if (/T00:00:00/.test(a.started_at)) continue; // no hour on gov.pl
    const hr = new Date(a.started_at).getHours();
    bins[hr][a.category === "air" ? "air" : "rest"]++;
    n++;
  }
  const max = Math.max(1, ...bins.map((b) => b.air + b.rest));
  const L = 8, R = 8, T = 8, B = 24, iw = W - L - R, ih = H - T - B, bw = iw / 24;
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.replaceChildren();
  const axis = s("g", { class: "axis" }, svg), grid = s("g", { class: "grid" }, svg);
  s("line", { x1: L, x2: W - R, y1: T + ih, y2: T + ih }, grid);
  bins.forEach((b, i) => {
    const x = L + i * bw + 2, w = bw - 4;
    const hr = (b.rest / max) * ih, ha = (b.air / max) * ih;
    if (b.rest) s("rect", { class: "b-rest", x, width: w, y: T + ih - hr, height: hr, rx: 2 }, svg);
    if (b.air) s("rect", { class: "b-air", x, width: w, y: T + ih - hr - ha, height: ha, rx: 2 }, svg);
    const r = s("rect", { class: "hov", x: L + i * bw, width: bw, y: T, height: ih }, svg);
    s("title", {}, r, `${String(i).padStart(2, "0")}:00–${String(i).padStart(2, "0")}:59: ${b.air + b.rest}${b.air ? `, z powietrza ${b.air}` : ""}`);
    if (i % (W < 600 ? 6 : 3) === 0) s("text", { x: L + i * bw + bw / 2, y: H - 6, "text-anchor": "middle" }, axis, `${String(i).padStart(2, "0")}:00`);
  });
  $("#hour-sub").textContent = `Godzina pierwszego komunikatu, czas polski; ${n} ${plural(n, "alert", "alerty", "alertów")} z podaną godziną`;
}

async function main() {
  RCB.strip();
  const [data, geo] = await Promise.all([getJSON("data/archive.json"), getJSON("geo/poland.json")]);
  const all = data.alerts.filter((a) => a.date >= "2021-01-01").sort((a, b) => b.started_at.localeCompare(a.started_at));
  const btns = [...document.querySelectorAll("#period button")];
  let period = new URLSearchParams(location.search).get("okres") || "365";
  function draw() {
    const p = period === "all" ? "all" : Number(period);
    const now = new Date();
    const cur = inPeriod(all, p, now);
    btns.forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.p === period)));
    stats(cur, p, now);
    timeChart(cur, p, now);
    const byV = countVoiv(cur.rows);
    heatMap(geo, byV);
    ranked($("#c-voiv"), Object.entries(byV).sort((a, b) => b[1] - a[1]).map(([v, n]) => ({ v, n })), (i) => VOIV[i.v]);
    const byC = {};
    for (const a of cur.rows) byC[a.category] = (byC[a.category] || 0) + 1;
    ranked($("#c-cat"), Object.entries(byC).sort((a, b) => b[1] - a[1]).map(([cat, n]) => ({ cat, n })), (i) => CAT[i.cat]);
    const names = Object.fromEntries(geo.powiaty.map((p) => [p.id, (p.city ? "" : "pow. ") + p.name]));
    const byP = {};
    for (const a of cur.rows) for (const p of a.powiaty) byP[p] = (byP[p] || 0) + 1;
    ranked($("#c-pow"), Object.entries(byP).sort((a, b) => b[1] - a[1]).slice(0, 10).map(([p, n]) => ({ p, n })),
      (i) => `${names[i.p] || i.p} · ${VOIV[i.p.split("/")[0]]}`);
    hourChart(cur);
    $("#span-note").textContent = `Ile Alertów RCB wysłano, gdzie i o jakiej porze. Archiwum: ${fmtN(all.length)} alertów od ${fmtDay(new Date(all[all.length - 1].started_at))}.`;
  }
  btns.forEach((b) => b.addEventListener("click", () => {
    period = b.dataset.p;
    const u = new URLSearchParams(location.search);
    u.set("okres", period);
    history.replaceState(null, "", "?" + u);
    draw();
  }));
  let rt;
  addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(draw, 150); });
  draw();
}

main().catch((e) => { $("#stats").replaceChildren(h("p", { class: "stat", text: "Nie udało się wczytać archiwum: " + e.message })); });
