// Alerty RCB — the place search of the map page: an address, a postal code (57-300) or coordinates move the map there.
// Coordinates are read here, with no request; an address and a postal code go to the public Nominatim of
// OpenStreetMap (https://nominatim.org, usage policy: at most one request a second, no search while typing),
// first in Poland, then anywhere (the flood of 09.2024 also hit Czechia). The texts are map.geo.* in docs/i18n-map.js.
// RCBGeo.parse() and RCBGeo.url() are plain functions, so tests/geosearch.test.mjs runs them in node.
"use strict";

const RCBGeo = (() => {
  const NOMINATIM = "https://nominatim.openstreetmap.org";
  const ZIP = /^(\d{2})[-–— ]?(\d{3})$/;
  const t = (k, p) => (typeof RCB !== "undefined" ? RCB.t(k, p) : k);

  // one coordinate: 50.4378 / 50,4378 / -16.5 / 50°26'16"N / 50 26 16.1 N / N 50.4378 -> { v, hemi } or null
  function coord(s) {
    s = s.trim().toUpperCase().replace(/[′’]/g, "'").replace(/[″”]|''/g, '"');
    let hemi = "", m = s.match(/^([NSEW])\s*(.*)$/);
    if (m) { hemi = m[1]; s = m[2]; } else if ((m = s.match(/^(.*?)\s*([NSEW])$/))) { hemi = m[2]; s = m[1]; }
    s = s.replace(/^([+-]?\d+),(\d+)$/, "$1.$2");
    m = s.match(/^([+-]?\d+(?:\.\d+)?)\s*°?\s*(?:(\d+(?:\.\d+)?)\s*'?\s*(?:(\d+(?:\.\d+)?)\s*"?)?)?$/);
    if (!m) return null;
    const deg = Number(m[1]), min = m[2] ? Number(m[2]) : 0, sec = m[3] ? Number(m[3]) : 0;
    if (min >= 60 || sec >= 60 || (m[2] && !Number.isInteger(deg))) return null;
    let v = Math.abs(deg) + min / 60 + sec / 3600;
    if (m[1].startsWith("-") || hemi === "S" || hemi === "W") v = -v;
    return { v, hemi };
  }

  // the two halves of a pair: "a; b", "a, b", "a,b", "a b", "50°26'N 16°39'E" (decimal commas too: "50,43 16,65")
  function halves(q) {
    let m = q.match(/^(.+?)\s*[;/|]\s*(.+)$/);
    if (m) return [m[1], m[2]];
    if (q.split(", ").length === 2) return q.split(", ");
    if ((q.match(/,/g) || []).length === 1 && !/\s/.test(q)) return q.split(",");
    m = q.match(/^(.*?\d.*?[NS])\s*(.*\d.*[EW])$/i) || q.match(/^(.*?\d.*?[EW])\s*(.*\d.*[NS])$/i)
      || q.match(/^([NS].*?)\s+([EW].*)$/i) || q.match(/^([EW].*?)\s+([NS].*)$/i);
    if (m) return [m[1], m[2]];
    const a = q.split(" ");
    return a.length === 2 ? a : null;
  }

  // what the visitor typed: { kind: "coords", lat, lon } | { kind: "zip", zip } | { kind: "text", q } | { kind: "bad", why }
  function parse(input) {
    const q = String(input || "").trim().replace(/\s+/g, " ");
    if (!q) return { kind: "bad", why: "empty" };
    const z = q.match(ZIP);
    if (z) return { kind: "zip", zip: `${z[1]}-${z[2]}` };
    if (/^[NSEW+\-\d\s.,;°'"′″’/|]+$/i.test(q) && /\d/.test(q)) {
      const hv = halves(q);
      const a = hv && coord(hv[0]), b = hv && coord(hv[1]);
      if (!a || !b) return { kind: "bad", why: "coords" };
      // "16.65E 50.43N" names its halves; otherwise latitude comes first, as in Google Maps and Nominatim
      let lat = a.v, lon = b.v;
      if (/[EW]/.test(a.hemi) || /[NS]/.test(b.hemi)) [lat, lon] = [b.v, a.v];
      if (Math.abs(lat) > 90 || Math.abs(lon) > 180) return { kind: "bad", why: "range" };
      return { kind: "coords", lat, lon };
    }
    if (q.length < 3) return { kind: "bad", why: "short" };
    return { kind: "text", q };
  }

  // the Nominatim request for a parsed query; pl=false widens it past Poland
  function url(p, lang = "pl", pl = true) {
    const s = new URLSearchParams({ format: "jsonv2", limit: "5", "accept-language": lang });
    if (p.kind === "zip") s.set("postalcode", p.zip); else s.set("q", p.q);
    if (pl) s.set("countrycodes", "pl");
    return `${NOMINATIM}/search?${s}`;
  }
  const reverseUrl = (lat, lon, lang = "pl") => `${NOMINATIM}/reverse?${new URLSearchParams({ format: "jsonv2", lat: String(lat), lon: String(lon), zoom: "14", "accept-language": lang })}`;

  // a short name: the first three parts of display_name without the postal code and the country
  function short(name) {
    const parts = String(name || "").split(", ");
    const country = parts.length > 1 ? parts.pop() : "";
    const kept = parts.filter((x) => !/^\d\d-\d{3}$/.test(x));
    // OSM names a house "1, Grunwaldzka, …": the number goes after its street, as an address is written
    for (let i = 0; i < kept.length - 1; i++) if (/^\d+[A-Za-z]?(\/\d+[A-Za-z]?)?$/.test(kept[i])) kept.splice(i, 2, `${kept[i + 1]} ${kept[i]}`);
    const out = kept.slice(0, 3).join(", ");
    return out || country;
  }
  // { lat, lon, name, bounds: [[s, w], [n, e]] | null } from one Nominatim result
  function place(x) {
    const b = (x.boundingbox || []).map(Number);
    return {
      lat: Number(x.lat), lon: Number(x.lon),
      name: short(x.display_name),
      full: x.display_name || "",
      bounds: b.length === 4 && b.every(Number.isFinite) ? [[b[0], b[2]], [b[1], b[3]]] : null,
    };
  }

  // Nominatim asks for no more than one request a second from one visitor
  let last = 0;
  async function ask(u) {
    const wait = last + 1100 - Date.now();
    if (wait > 0) await new Promise((ok) => setTimeout(ok, wait));
    last = Date.now();
    const r = await fetch(u, { headers: { Accept: "application/json" } });
    if (!r.ok) throw new Error(t("map.geo.svc", { status: r.status }));
    return r.json();
  }
  async function search(p, lang) {
    let res = await ask(url(p, lang, true));
    if (!res.length && p.kind === "text") res = await ask(url(p, lang, false));
    return res.map(place);
  }
  async function reverse(lat, lon, lang) {
    const j = await ask(reverseUrl(lat, lon, lang));
    return j && j.display_name ? short(j.display_name) : "";
  }

  // ---------- the control on the map ----------
  // a search field in the top right corner of the map; Enter or the button searches, the map flies to the place
  // and a marker shows it; more than one match gives a list to pick from; Escape or × clears it
  function control(map, opts = {}) {
    const fly = opts.fly || ((ll, z) => map.flyTo(ll, z, { duration: 0.8 }));
    const C = L.Control.extend({
      options: { position: "topright" },
      onAdd() {
        const box = L.DomUtil.create("div", "leaflet-control geo-search");
        const form = document.createElement("form");
        form.setAttribute("role", "search");
        form.id = "geo-form";
        const label = document.createElement("label");
        label.className = "visually-hidden";
        label.htmlFor = "geo-q";
        label.textContent = t("map.geo.label");
        const input = document.createElement("input");
        Object.assign(input, { type: "search", id: "geo-q", placeholder: t("map.geo.ph"), autocomplete: "off", spellcheck: false });
        input.setAttribute("enterkeyhint", "search");
        input.setAttribute("aria-describedby", "geo-note");
        const go = document.createElement("button");
        go.type = "submit";
        go.className = "btn geo-go";
        go.setAttribute("aria-label", t("map.geo.go"));
        go.title = t("map.geo.go");
        go.innerHTML = '<svg width="16" height="16" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><circle cx="7" cy="7" r="4.5"/><path d="m10.5 10.5 3.5 3.5"/></svg>';
        const clear = document.createElement("button");
        clear.type = "button";
        clear.className = "btn geo-clear";
        clear.hidden = true;
        clear.setAttribute("aria-label", t("map.geo.clear"));
        clear.title = t("map.geo.clear");
        clear.textContent = "×";
        form.append(label, input, clear, go);
        const note = document.createElement("p");
        note.id = "geo-note";
        note.className = "geo-note";
        note.setAttribute("role", "status");
        note.hidden = true;
        const list = document.createElement("ul");
        list.className = "geo-results";
        list.id = "geo-results";
        list.hidden = true;
        box.append(form, note, list);
        L.DomEvent.disableClickPropagation(box);
        L.DomEvent.disableScrollPropagation(box);

        let marker = null, seq = 0;
        const say = (text, bad = false) => { note.textContent = text; note.hidden = !text; note.classList.toggle("bad", bad); };
        // a name from OpenStreetMap is data: Leaflet writes string content through innerHTML, so it goes in as an element
        const tipText = (text) => { const sp = document.createElement("span"); sp.textContent = text; return sp; };
        const lang = () => (typeof RCB !== "undefined" ? RCB.lang() : "pl");
        function show(p) {
          list.hidden = true;
          if (marker) map.removeLayer(marker);
          const shown = p.name || `${p.lat.toFixed(5)}, ${p.lon.toFixed(5)}`;
          marker = L.circleMarker([p.lat, p.lon], { radius: 8, weight: 3, className: "geo-pin", interactive: true })
            .bindTooltip(tipText(shown), { direction: "top", offset: [0, -8], className: "tip", permanent: false })
            .addTo(map);
          clear.hidden = false;
          // a town or a postal code fills the view; an address or a point gets a street zoom
          if (p.bounds) map.flyToBounds(p.bounds, { maxZoom: 15, padding: [24, 24], duration: 0.8 });
          else fly([p.lat, p.lon], Math.max(map.getZoom(), 14));
          say(t("map.geo.found", { name: shown, lat: p.lat.toFixed(5), lon: p.lon.toFixed(5) }));
          box.dispatchEvent(new CustomEvent("geo:found", { bubbles: true, detail: p }));
        }
        function reset() {
          seq++;
          if (marker) { map.removeLayer(marker); marker = null; }
          input.value = "";
          list.hidden = true;
          clear.hidden = true;
          say("");
        }
        form.addEventListener("submit", async (e) => {
          e.preventDefault();
          const p = parse(input.value);
          const my = ++seq;
          list.hidden = true;
          if (p.kind === "bad") { say(t(`map.geo.bad.${p.why}`), true); return; }
          if (p.kind === "coords") {
            const pt = { lat: p.lat, lon: p.lon, name: "", bounds: null };
            show(pt);
            // the name of the place, when Nominatim knows it; the map has moved already
            reverse(p.lat, p.lon, lang()).then((name) => {
              if (my !== seq || !name || !marker) return;
              marker.setTooltipContent(tipText(name));
              say(t("map.geo.found", { name, lat: p.lat.toFixed(5), lon: p.lon.toFixed(5) }));
            }).catch(() => {});
            return;
          }
          say(t("map.geo.searching"));
          go.disabled = true;
          let res;
          try { res = await search(p, lang()); }
          catch (err) { if (my === seq) say(t("map.geo.fail", { msg: err.message }), true); return; }
          finally { go.disabled = false; }
          if (my !== seq) return;
          if (!res.length) { say(t(p.kind === "zip" ? "map.geo.nozip" : "map.geo.none"), true); return; }
          if (p.kind === "zip") res[0].name = `${p.zip}, ${res[0].name}`;
          show(res[0]);
          if (res.length > 1) {
            list.replaceChildren(...res.map((x, i) => {
              const li = document.createElement("li");
              const b = document.createElement("button");
              b.type = "button";
              b.className = "link";
              b.textContent = x.name;
              b.title = x.full;
              if (i === 0) b.setAttribute("aria-current", "true");
              b.addEventListener("click", () => { list.querySelectorAll("[aria-current]").forEach((y) => y.removeAttribute("aria-current")); b.setAttribute("aria-current", "true"); show(x); list.hidden = false; });
              li.append(b);
              return li;
            }));
            list.hidden = false;
          }
        });
        clear.addEventListener("click", () => { reset(); input.focus(); });
        input.addEventListener("keydown", (e) => { if (e.key === "Escape") reset(); });
        this._input = input;
        return box;
      },
    });
    const c = new C();
    c.addTo(map);
    return c;
  }

  return { parse, url, reverseUrl, short, place, search, reverse, control };
})();
