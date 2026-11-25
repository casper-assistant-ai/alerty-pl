// Alerty RCB — Copernicus Sentinel-2 (10 m, true colour) under the map, through the public, keyless Microsoft
// Planetary Computer (STAC search + titiler mosaics, CORS open). A satellite passes Poland every 2–5 days, so
// the layer shows one day: the scenes of the view's centre are searched for the period and AROUND days on each
// side; the clearest day comes up by itself (the newest clear one inside the period, else the clear one nearest
// to it, else the least cloudy one), and every day of the period plus the clear days around it can be picked.
// No interface text here: app.js reads the words from docs/i18n-map.js.
"use strict";

const RCBSentinel = (() => {
  const PC = "https://planetarycomputer.microsoft.com/api";
  const STAC = PC + "/stac/v1/search";
  const DATA = PC + "/data/v1";
  const COLL = "sentinel-2-l2a";
  const CLEAR = 20;   // a scene with at most this much cloud (per cent of the whole 110 km tile) counts as clear
  const AROUND = 30;  // days searched before and after the period for the nearest clear scene
  const LIMIT = 300;  // scenes per search, newest first (a long period keeps its end)
  const MIN_ZOOM = 9; // the mosaic service answers 204 (no tile) below zoom 9
  const DAY = 86400000;
  const shift = (iso, n) => new Date(Date.parse(iso + "T12:00:00Z") + n * DAY).toISOString().slice(0, 10);
  const gap = (a, b) => Math.round((Date.parse(b + "T12:00:00Z") - Date.parse(a + "T12:00:00Z")) / DAY);
  const attr = (day) => `Contains modified <a href="https://dataspace.copernicus.eu/">Copernicus Sentinel</a> data ${day.slice(0, 4)}` +
    ` (Sentinel-2 L2A ${day.split("-").reverse().join(".")}) · <a href="https://planetarycomputer.microsoft.com/dataset/sentinel-2-l2a">Microsoft Planetary Computer</a>`;

  const wait = (ms) => new Promise((ok) => setTimeout(ok, ms));
  // one dropped request is asked again (as in wayback.js), up to three times
  async function post(url, body, attempts = 3) {
    for (let i = 1; ; i++) {
      try {
        const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
        if (!r.ok) throw new Error("Planetary Computer: " + r.status);
        return await r.json();
      } catch (e) {
        if (i >= attempts) throw e;
        await wait(500 * i);
      }
    }
  }

  // the STAC search: scenes over one point between two days, newest first, only the fields used
  function searchBody(lat, lng, from, to) {
    return {
      collections: [COLL], intersects: { type: "Point", coordinates: [+lng.toFixed(4), +lat.toFixed(4)] },
      datetime: `${from}T00:00:00Z/${to}T23:59:59Z`, limit: LIMIT,
      sortby: [{ field: "datetime", direction: "desc" }],
      fields: { include: ["id", "properties.datetime", "properties.eo:cloud_cover"], exclude: ["assets", "links", "geometry", "bbox"] },
    };
  }

  // scenes -> days, newest first: { day, cloud (the clearest scene of that day, rounded), n }
  function daysOf(features) {
    const by = new Map();
    for (const f of features || []) {
      const p = f.properties || {}, day = String(p.datetime || "").slice(0, 10);
      if (!/^\d{4}-\d\d-\d\d$/.test(day)) continue;
      const c = Number.isFinite(p["eo:cloud_cover"]) ? p["eo:cloud_cover"] : 100;
      const d = by.get(day) || { day, cloud: 100, n: 0 };
      d.cloud = Math.min(d.cloud, Math.round(c)); d.n++;
      by.set(day, d);
    }
    return [...by.values()].sort((a, b) => b.day.localeCompare(a.day));
  }

  // what the list offers: every day inside the period, and the clear days around it
  const inside = (d, from, to) => d.day >= from && d.day <= to;
  const offer = (days, from, to) => days.filter((d) => inside(d, from, to) || d.cloud <= CLEAR);
  // how far a day lies from the period (0 inside)
  const away = (day, from, to) => (day < from ? gap(day, from) : day > to ? gap(to, day) : 0);

  // the day shown by itself: the newest clear day of the period; else the clear day nearest to the period
  // (the later one on a tie: after an event rather than before it); else the least cloudy day; null for none
  function pick(days, from, to) {
    if (!days.length) return null;
    const clearIn = days.filter((d) => inside(d, from, to) && d.cloud <= CLEAR);
    if (clearIn.length) return clearIn[0];
    const clear = days.filter((d) => d.cloud <= CLEAR)
      .sort((a, b) => away(a.day, from, to) - away(b.day, from, to) || b.day.localeCompare(a.day));
    if (clear.length) return clear[0];
    return [...days].sort((a, b) => a.cloud - b.cloud || away(a.day, from, to) - away(b.day, from, to))[0];
  }

  // the days of the view's centre for a period (cached per spot of ~1 km and period)
  const cache = new Map();
  function scenes(center, from, to) {
    const a = shift(from, -AROUND), b = shift(to, AROUND);
    const key = `${center.lat.toFixed(2)},${center.lng.toFixed(2)},${a},${b}`;
    if (!cache.has(key)) {
      cache.set(key, post(STAC, searchBody(center.lat, center.lng, a, b)).then((d) => daysOf(d.features))
        .catch((e) => { cache.delete(key); throw e; }));
    }
    return cache.get(key);
  }

  // a mosaic of all the scenes of one day, the clearest on top; the service keeps a registered search a day,
  // so it is registered once per page and day and again when the page is older than that
  const mosaics = new Map();
  const mosaicBody = (day) => ({
    collections: [COLL], "filter-lang": "cql2-json",
    filter: { op: "anyinteracts", args: [{ property: "datetime" }, { interval: [`${day}T00:00:00Z`, `${day}T23:59:59Z`] }] },
    sortby: [{ field: "eo:cloud_cover", direction: "asc" }],
  });
  async function mosaic(day) {
    const m = mosaics.get(day);
    if (m && Date.now() - m.at < 20 * 3600000) return m.id;
    const r = await post(DATA + "/mosaic/register", mosaicBody(day));
    const id = r.searchid || r.id;
    if (!id) throw new Error("Planetary Computer: no mosaic id");
    mosaics.set(day, { id, at: Date.now() });
    return id;
  }
  const tileURL = (id) => `${DATA}/mosaic/${encodeURIComponent(id)}/tiles/WebMercatorQuad/{z}/{x}/{y}@1x?collection=${COLL}&assets=visual&nodata=0&format=png`;
  async function layer(day) {
    const id = await mosaic(day);
    return L.tileLayer(tileURL(id), { minZoom: MIN_ZOOM, maxNativeZoom: 14, maxZoom: 19, attribution: attr(day) });
  }

  return { CLEAR, AROUND, MIN_ZOOM, searchBody, daysOf, offer, pick, away, scenes, mosaicBody, tileURL, layer, attr };
})();
