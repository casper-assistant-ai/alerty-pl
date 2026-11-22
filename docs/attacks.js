// Alerty RCB — missiles and drones that entered Polish airspace, on the map page.
// events/incursions.json is a hand-kept list of the confirmed cases since 2022, each with its sources.
// The days of those cases are red on the day slider and in a row of dates under it; opening such a day
// (a click, or ?dzien=…) plays the case on the map: missile and drone icons fly along their approximate
// routes, then the places where they exploded, crashed, were shot down or left debris stay marked.
// Without motion (prefers-reduced-motion) the routes and places are drawn at once.
"use strict";
(() => {
  const { $, h } = RCB;
  const fmtISO = (iso) => iso.split("-").reverse().join(".");
  const still = matchMedia("(prefers-reduced-motion: reduce)");

  const KIND = { missile: "rakieta", drone: "dron" };
  const END = {
    explosion: "wybuch", crash: "upadek", shotdown: "zestrzelenie", debris: "szczątki",
    left_airspace: "opuścił przestrzeń RP", not_found: "nie odnaleziono",
  };
  // from = the country that launched it, via = the country it flew over before Poland (never the other way round)
  const FROM = { Russia: "z Rosji", "Russia-Kaliningrad": "z obwodu królewieckiego (Rosja)", Belarus: "z Białorusi" };
  const VIA = { Ukraine: "nad Ukrainą", Belarus: "nad Białorusią" };
  function origin(w) {
    if (w.role === "air_defense") return "podczas rosyjskiego ataku";
    const m = w.kind === "missile", out = [];
    if (FROM[w.from]) out.push((m ? "odpalona " : "wystrzelony ") + FROM[w.from]);
    if (VIA[w.via]) out.push((m ? "przeleciała " : "przeleciał ") + VIA[w.via]);
    return out.join(", ");
  }

  // icons point north (up); the flight turns them along the route
  const ICON = {
    missile: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 1.5c1.6 1.4 2.3 3.3 2.3 5.4V15l2.9 3.3v2.2l-3-1.2-.5 2.2h-3.4l-.5-2.2-3 1.2v-2.2L9.7 15V6.9c0-2.1.7-4 2.3-5.4z"/></svg>',
    drone: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2.2 22.6 19.6l-1.2 1.2-5.6-2.3-.7 2.2h-6.2l-.7-2.2-5.6 2.3-1.2-1.2z"/></svg>',
  };
  const MARK = {
    explosion: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 1 2.2 6.3 6-3-2.6 6.2 5.4 1.7-5.6 2.1 3 5.6-6-2.6L12 23l-2.4-5.7-6 2.6 3-5.6L1 12.2l5.4-1.7-2.6-6.2 6 3z"/></svg>',
    crash: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5.6 3.5 12 9.9l6.4-6.4 2.1 2.1-6.4 6.4 6.4 6.4-2.1 2.1-6.4-6.4-6.4 6.4-2.1-2.1 6.4-6.4-6.4-6.4z"/></svg>',
    shotdown: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2a10 10 0 1 1 0 20 10 10 0 0 1 0-20zm0 3a7 7 0 0 0-1.5 13.8V14h3v4.8A7 7 0 0 0 12 5zm-1.5 0v4.8h3V5.2zM5.2 10.5h4.6v3H5.2zm9 0h4.6v3h-4.6z"/></svg>',
    debris: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m4 6 5-2 1 4-4 2zm9-3 5 1-1 5-4-1zm1 9 6-1 1 6-5 1zm-10 2 5-1 2 5-5 2z"/></svg>',
  };
  MARK.left_airspace = MARK.not_found = '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="5" fill="none" stroke="currentColor" stroke-width="2.5" stroke-dasharray="3 2.5"/></svg>';

  const R = { events: [], byDay: new Map(), map: null, api: null, layer: null, raf: 0, current: null, open: null };

  // ---------- the slider: red days ----------
  function ticks() {
    const box = $("#raid-ticks"), api = R.api;
    if (!box || !api) return;
    box.replaceChildren(...[...R.byDay.keys()].map((day) => {
      const x = api.frac(day);
      if (!(x >= 0 && x <= 1)) return null;
      const evs = R.byDay.get(day);
      const b = h("button", { type: "button", class: "raid-tick", style: `--x:${x.toFixed(5)}`, "data-day": day,
        title: `${fmtISO(day)}: ${evs.map((e) => e.title_pl).join("; ")}`, "aria-label": `${fmtISO(day)}: ${evs.map((e) => e.title_pl).join("; ")}` });
      b.addEventListener("pointerdown", (ev) => ev.stopPropagation());
      b.addEventListener("click", () => api.setDay(day));
      return b;
    }).filter(Boolean));
    const row = $("#raid-days");
    row.replaceChildren(h("span", { class: "raid-days-t", text: "Zaloty rakiet i dronów nad Polską:" }), ...[...R.byDay.keys()].map((day) => {
      const b = h("button", { type: "button", class: "raid-day mono", "data-day": day, text: fmtISO(day), title: R.byDay.get(day).map((e) => e.title_pl).join("; ") });
      b.addEventListener("click", () => api.setDay(day));
      return b;
    }));
    row.hidden = false;
  }

  function mark(day) {
    document.querySelectorAll(".raid-tick, .raid-day").forEach((b) => b.classList.toggle("on", b.dataset.day === day));
    $("#day-label")?.classList.toggle("raid", R.byDay.has(day));
  }

  // ---------- geometry ----------
  // the route in Web Mercator pixels at zoom 8: heading as on screen, speed the same at any zoom
  const Z = 8;
  function track(path) {
    const pts = path.map((p) => R.map.project(L.latLng(p), Z));
    const cum = [0];
    for (let i = 1; i < pts.length; i++) cum.push(cum[i - 1] + pts[i].distanceTo(pts[i - 1]));
    return { pts, cum, len: cum[cum.length - 1] || 1 };
  }
  function at(t, f) {
    const d = f * t.len;
    let i = 1;
    while (i < t.cum.length - 1 && t.cum[i] < d) i++;
    const a = t.pts[i - 1], b = t.pts[i] || a, seg = (t.cum[i] - t.cum[i - 1]) || 1;
    const k = Math.min(1, Math.max(0, (d - t.cum[i - 1]) / seg));
    const p = L.point(a.x + (b.x - a.x) * k, a.y + (b.y - a.y) * k);
    return { p, deg: Math.atan2(b.x - a.x, a.y - b.y) * 180 / Math.PI, i, k };
  }
  // a small sideways shift, so a swarm on one route shows several icons
  function shifted(path, off) {
    if (!off) return path;
    return path.map((p, i) => {
      const a = path[Math.max(0, i - 1)], b = path[Math.min(path.length - 1, i + 1)];
      const dy = b[0] - a[0], dx = (b[1] - a[1]) * Math.cos(p[0] * Math.PI / 180), l = Math.hypot(dx, dy) || 1;
      return [p[0] + (dx / l) * off, p[1] - (dy / l) * off / Math.cos(p[0] * Math.PI / 180)];
    });
  }

  // ---------- the flight ----------
  const icon = (kind) => L.divIcon({ className: "raid-ico k-" + kind, html: `<span>${ICON[kind] || ICON.drone}</span>`, iconSize: [30, 30], iconAnchor: [15, 15] });
  const endIcon = (type, burst) => L.divIcon({ className: `raid-end e-${type}${burst ? " burst" : ""}`, html: `<span>${MARK[type] || MARK.crash}</span>`, iconSize: [24, 24], iconAnchor: [12, 12] });

  function tipFor(p, ev) {
    return h("div", {}, h("b", { text: (END[p.type] || p.type) + (p.place ? ": " + p.place : "") }),
      p.note_pl ? h("div", { text: p.note_pl }) : null, h("div", { class: "mono muted", text: fmtISO(ev.date) }));
  }

  function stop() {
    cancelAnimationFrame(R.raf);
    R.raf = 0;
    if (R.layer) R.layer.clearLayers();
  }

  function play(ev) {
    stop();
    const layer = R.layer, flights = [], pts = ev.points || [];
    let slot = 0;
    for (const w of ev.weapons || []) {
      if (!w.path || w.path.length < 2) continue;
      const copies = Math.min(Math.max(1, w.count || 1), 4);
      for (let c = 0; c < copies; c++) {
        const off = copies > 1 ? (c - (copies - 1) / 2) * 0.025 : 0;
        const path = shifted(w.path, off);
        const t = track(path);
        flights.push({ w, path, t, delay: slot * 450 + c * 250, dur: Math.min(8000, Math.max(3000, t.len * 5)), done: false,
          route: c ? null : L.polyline(w.path, { pane: "raid", className: "raid-route k-" + w.kind, interactive: false }).addTo(layer),
          start: c || !w.launch ? null : L.circleMarker(w.path[0], { pane: "raid", radius: 5, weight: 2, color: "#b3122e", fillColor: "#fff", fillOpacity: 1, className: "raid-start" })
            .bindTooltip(`Start: ${w.launch.area_pl}${w.launch.certain ? "" : " (miejsce umowne)"}`, { className: "tip", direction: "top" }).addTo(layer),
          trail: L.polyline([], { pane: "raid", className: "raid-trail k-" + w.kind, interactive: false }).addTo(layer),
          m: null, label: copies > 1 && c === copies - 1 && w.count > copies ? w.count : 0 });
      }
      slot++;
    }
    const bounds = L.latLngBounds([]);
    flights.forEach((f) => f.path.forEach((p) => bounds.extend(p)));
    pts.forEach((p) => bounds.extend([p.lat, p.lon]));
    if (bounds.isValid()) R.map.fitBounds(bounds, { padding: [36, 36], maxZoom: 9, animate: false });
    const showPoints = () => {
      for (const p of pts) L.marker([p.lat, p.lon], { pane: "raid", icon: endIcon(p.type, !still.matches), keyboard: false })
        .bindTooltip(() => tipFor(p, ev), { className: "tip", direction: "top", offset: [0, -10] }).addTo(layer);
    };
    const land = (f) => {
      f.done = true;
      f.trail.setLatLngs(f.path);
      if (f.m) layer.removeLayer(f.m);
      const e = f.w.end;
      if (e && (e.lat == null || pts.some((p) => Math.abs(p.lat - e.lat) < 1e-3 && Math.abs(p.lon - e.lon) < 1e-3))) return;
      const ll = e && e.lat != null ? [e.lat, e.lon] : f.path[f.path.length - 1];
      L.marker(ll, { pane: "raid", icon: endIcon(e ? e.type : "crash", !still.matches), keyboard: false })
        .bindTooltip(() => tipFor({ type: e ? e.type : "crash", place: e && e.place, note_pl: f.w.label_pl }, ev), { className: "tip", direction: "top", offset: [0, -10] })
        .addTo(layer);
    };
    if (still.matches || !flights.length) { flights.forEach(land); showPoints(); return; }
    let t0 = 0, shown = false;
    const total = Math.max(...flights.map((f) => f.delay + f.dur));
    const frame = (now) => {
      if (!t0) t0 = now;
      const el = now - t0;
      for (const f of flights) {
        if (f.done || el < f.delay) continue;
        const k = Math.min(1, (el - f.delay) / f.dur);
        if (k >= 1) { land(f); continue; }
        const a = at(f.t, k), ll = R.map.unproject(a.p, Z);
        if (!f.m) {
          f.m = L.marker(ll, { pane: "raid", icon: icon(f.w.kind), interactive: false, keyboard: false }).addTo(layer);
          if (f.label) f.m.bindTooltip("×" + f.label, { permanent: true, direction: "right", className: "raid-n", offset: [10, 0] });
        } else f.m.setLatLng(ll);
        const s = f.m.getElement()?.firstChild;
        if (s) s.style.transform = `rotate(${a.deg.toFixed(1)}deg)`;
        f.trail.setLatLngs([...f.path.slice(0, a.i), ll]);
      }
      if (!shown && el > total - 600) { shown = true; showPoints(); }
      if (flights.every((f) => f.done)) { R.raf = 0; if (!shown) showPoints(); return; }
      R.raf = requestAnimationFrame(frame);
    };
    R.raf = requestAnimationFrame(frame);
  }

  // ---------- the card above the map ----------
  function card(ev, list) {
    const box = $("#raid");
    const kinds = [...new Set((ev.weapons || []).map((w) => w.kind))];
    const weapons = (ev.weapons || []).map((w) => h("li", {},
      h("i", { class: "raid-sw k-" + w.kind, "aria-hidden": "true" }),
      `${w.label_pl}${w.count > 1 ? " ×" + w.count : ""}${origin(w) ? ", " + origin(w) : ""}${w.end ? " → " + (END[w.end.type] || w.end.type) + (w.end.place ? " (" + w.end.place + ")" : "") : ""}`));
    const replay = h("button", { type: "button", class: "btn", text: still.matches ? "Pokaż" : "Odtwórz ponownie" });
    replay.addEventListener("click", () => play(ev));
    const others = list.length > 1 ? h("div", { class: "raid-pick" }, ...list.map((e) => {
      const b = h("button", { type: "button", class: "btn" + (e === ev ? " on" : ""), text: e.title_pl });
      b.addEventListener("click", () => open(e, list));
      return b;
    })) : null;
    box.replaceChildren(...[
      h("div", { class: "raid-head" },
        h("span", { class: "raid-flag mono", text: fmtISO(ev.date) + (ev.time_local ? " " + ev.time_local : "") }),
        h("h2", { text: ev.title_pl }), replay),
      others,
      h("p", { class: "raid-sum", text: ev.summary_pl }),
      weapons.length > 4
        ? h("details", { class: "raid-src raid-wd" }, h("summary", { text: `Obiekty (${weapons.length})` }), h("ul", { class: "raid-w" }, ...weapons))
        : weapons.length ? h("ul", { class: "raid-w" }, ...weapons) : null,
      h("ul", { class: "raid-legend mono", "aria-label": "Legenda" },
        ...kinds.map((k) => h("li", {}, h("i", { class: "raid-sw k-" + k, "aria-hidden": "true" }), KIND[k] || k)),
        ...[...new Set([...(ev.points || []).map((p) => p.type), ...(ev.weapons || []).map((w) => w.end && w.end.type)].filter(Boolean))]
          .map((t) => h("li", {}, h("i", { class: "raid-em e-" + t, "aria-hidden": "true" }), END[t] || t)),
        h("li", {}, h("i", { class: "raid-dash", "aria-hidden": "true" }), "trasa orientacyjna")),
      h("p", { class: "raid-note muted", text: ev.route_note_pl || "Trasy są orientacyjne: wojsko nie publikuje dokładnych torów lotu." }),
      h("details", { class: "raid-src" }, h("summary", { text: `Źródła (${ev.sources.length})` }),
        h("ul", {}, ...ev.sources.map((s) => h("li", {}, h("a", { href: s.url, target: "_blank", rel: "noopener", text: s.title }),
          h("span", { class: "muted mono", text: ` · ${s.publisher}${s.date ? ", " + fmtISO(s.date) : ""}` })))))].filter(Boolean));
    box.hidden = false;
  }

  function open(ev, list) {
    R.open = ev;
    R.map.getContainer().classList.add("raid-on");
    card(ev, list);
    play(ev);
  }

  function onDay(day) {
    mark(day);
    const list = R.byDay.get(day);
    if (!list) {
      R.open = null;
      stop();
      R.map.getContainer().classList.remove("raid-on");
      const box = $("#raid");
      if (box) box.hidden = true;
      return;
    }
    if (R.open && R.open.date === day) return;
    open(list[0], list);
  }

  // ---------- start ----------
  async function start(api) {
    R.api = api;
    R.map = api.map;
    R.map.createPane("raid").style.zIndex = 640;
    R.layer = L.layerGroup().addTo(R.map);
    const data = await RCB.getJSON("events/incursions.json");
    R.events = data.events.filter((e) => e.sources && e.sources.length).sort((a, b) => a.date.localeCompare(b.date));
    for (const e of R.events) (R.byDay.get(e.date) || R.byDay.set(e.date, []).get(e.date)).push(e);
    ticks();
    onDay(api.day());
    addEventListener("rcb:day", (e) => onDay(e.detail.day));
    addEventListener("rcb:range", ticks);
  }

  const go = (api) => start(api).catch((e) => console.error("incursions:", e));
  if (window.RCBMap) go(window.RCBMap); else addEventListener("rcb:ready", (e) => go(e.detail), { once: true });
})();
