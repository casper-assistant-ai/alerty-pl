// Alerty RCB — Esri World Imagery Wayback, shared by the map (app.js) and the comparison page (porownaj.js).
// Every Wayback release is a full world mosaic; most tiles in a release are copies of an older one. The tilemap
// of a release names the release a tile really comes from, so walking back from the newest release gives the
// distinct images of one spot. The metadata service of a release tells when and by whom an image was taken.
"use strict";

const RCBWayback = (() => {
  const CONFIG = "https://s3-us-west-2.amazonaws.com/config.maptiles.arcgis.com/waybackconfig.json";
  const BASE = "https://wayback.maptiles.arcgis.com/arcgis/rest/services/World_Imagery";
  const ATTR = '<a href="https://livingatlas.arcgis.com/wayback/">Esri World Imagery Wayback</a>: Esri, Maxar, Earthstar Geographics, GUGiK';
  const ISO = /^\d{4}-\d\d-\d\d$/;

  let list = null, loading = null;
  // the releases, newest first: { id, date (publication, YYYY-MM-DD), meta (metadata service URL) }
  function config() {
    if (list) return Promise.resolve(list);
    loading = loading || fetch(CONFIG).then((r) => {
      if (!r.ok) throw new Error("waybackconfig: " + r.status);
      return r.json();
    }).then((cfg) => {
      list = Object.entries(cfg).map(([k, v]) => ({ id: +k, date: (v.itemTitle.match(/\d{4}-\d\d-\d\d/) || [""])[0], meta: v.metadataLayerUrl }))
        .filter((x) => x.date).sort((a, b) => b.date.localeCompare(a.date));
      return list;
    }).catch((e) => { loading = null; throw e; });
    return loading;
  }

  // a new layer for each release: Leaflet 1.9's setUrl() redraws at a fractional zoom (6.25) and asks for wrong tiles
  const layer = (id, opts = {}) => L.tileLayer(`${BASE}/WMTS/1.0.0/default028mm/MapServer/tile/${id}/{z}/{y}/{x}`, {
    maxZoom: 19, maxNativeZoom: 19, attribution: ATTR, ...opts,
  });

  // the tile under the centre of the view
  function tileAt(map) {
    const z = Math.max(4, Math.min(17, Math.round(map.getZoom())));
    const c = map.getCenter(), n = 2 ** z;
    const x = Math.floor((c.lng + 180) / 360 * n);
    const lat = c.lat * Math.PI / 180;
    const y = Math.floor((1 - Math.log(Math.tan(lat) + 1 / Math.cos(lat)) / Math.PI) / 2 * n);
    return { z, y, x };
  }

  // the distinct images of a tile, newest first (about 5 at country zoom, 20+ in a town)
  const cache = new Map();
  async function local(z, y, x) {
    const key = `${z}/${y}/${x}`;
    if (cache.has(key)) return cache.get(key);
    const rel = await config();
    const out = [];
    let i = 0;
    while (i < rel.length && out.length < 40) {
      const j = await (await fetch(`${BASE}/MapServer/tilemap/${rel[i].id}/${key}`)).json();
      if (!j.data || !j.data[0]) break;
      const id = (j.select && j.select[0]) || rel[i].id;
      const k = rel.findIndex((r) => r.id === id);
      if (k < 0) break;
      out.push(rel[k]);
      i = k + 1;
    }
    cache.set(key, out);
    return out;
  }
  const atView = (map) => { const t = tileAt(map); return local(t.z, t.y, t.x); };

  // the image to show for a day: the newest published on or before it, else the oldest one
  const onOrBefore = (rels, day) => rels.find((r) => r.date <= day) || rels[rels.length - 1];
  // a release by its date (?zdjecie=YYYY-MM-DD), or null
  const byDate = (rels, day) => (ISO.test(day || "") ? onOrBefore(rels, day) : null);

  // when the image of a release at a point was taken: { day: YYYY-MM-DD, source, res (m) } or null.
  // The metadata service has one layer per resolution; layer 23 - zoom matches the tiles of that zoom.
  const metaCache = new Map();
  async function captured(rel, latlng, zoom) {
    if (!rel || !rel.meta) return null;
    const lid = Math.max(0, Math.min(13, 23 - Math.round(zoom)));
    const key = `${rel.id}/${lid}/${latlng.lat.toFixed(4)},${latlng.lng.toFixed(4)}`;
    if (metaCache.has(key)) return metaCache.get(key);
    const q = new URLSearchParams({
      geometry: `${latlng.lng},${latlng.lat}`, geometryType: "esriGeometryPoint", inSR: "4326",
      spatialRel: "esriSpatialRelIntersects", outFields: "SRC_DATE,SRC_RES,NICE_DESC", returnGeometry: "false", f: "json",
    });
    const j = await (await fetch(`${rel.meta}/${lid}/query?${q}`)).json();
    const a = j.features && j.features[0] && j.features[0].attributes;
    const s = a && String(a.SRC_DATE || "");
    const out = s && /^\d{8}$/.test(s) ? { day: `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}`, source: a.NICE_DESC || "", res: a.SRC_RES } : null;
    metaCache.set(key, out);
    return out;
  }

  return { ATTR, config, layer, tileAt, local, atView, onOrBefore, byDate, captured };
})();
