// Node test for docs/geosearch.js — the place search of the map page (no npm, just node:test).
// CI runs it with node --test tests/*.test.mjs and through tests/test_geosearch_js.py; alone: node --test tests/geosearch.test.mjs
import { readFileSync } from "node:fs";
import { test } from "node:test";
import assert from "node:assert/strict";

const src = readFileSync(new URL("../docs/geosearch.js", import.meta.url), "utf8");
const G = new Function(`${src}\n;return RCBGeo;`)();
const near = (got, lat, lon) => {
  assert.equal(got.kind, "coords", JSON.stringify(got));
  assert.ok(Math.abs(got.lat - lat) < 1e-4 && Math.abs(got.lon - lon) < 1e-4, `${got.lat}, ${got.lon} is not ${lat}, ${lon}`);
};

test("decimal coordinates in every common form, latitude first", () => {
  for (const q of ["50.4378, 16.6537", "50.4378,16.6537", "50.4378 16.6537", "50,4378 16,6537", "50,4378, 16,6537",
    "50.4378; 16.6537", "  50.4378  16.6537 ", "N50.4378 E16.6537", "50.4378N 16.6537E", "50.4378 N, 16.6537 E"]) {
    near(G.parse(q), 50.4378, 16.6537);
  }
});

test("hemisphere letters may name the halves in any order; S and W are negative", () => {
  near(G.parse("16.6537E 50.4378N"), 50.4378, 16.6537);
  near(G.parse("-33.86, 151.21"), -33.86, 151.21);
  near(G.parse("40.7128 N, 74.0060 W"), 40.7128, -74.006);
});

test("degrees, minutes and seconds", () => {
  near(G.parse(`50°26'16"N 16°39'13"E`), 50 + 26 / 60 + 16 / 3600, 16 + 39 / 60 + 13 / 3600);
  near(G.parse("50°26′16″N, 16°39′13″E"), 50 + 26 / 60 + 16 / 3600, 16 + 39 / 60 + 13 / 3600);
  near(G.parse("50° 26.27' N 16° 39.22' E"), 50 + 26.27 / 60, 16 + 39.22 / 60);
});

test("a Polish postal code, with or without its dash", () => {
  assert.deepEqual(G.parse("57-300"), { kind: "zip", zip: "57-300" });
  assert.deepEqual(G.parse(" 57300 "), { kind: "zip", zip: "57-300" });
  assert.deepEqual(G.parse("57 300"), { kind: "zip", zip: "57-300" });
});

test("anything else is an address; nothing, two letters or impossible numbers are refused", () => {
  assert.deepEqual(G.parse("Kłodzko"), { kind: "text", q: "Kłodzko" });
  assert.deepEqual(G.parse("Nysa, Rynek 1"), { kind: "text", q: "Nysa, Rynek 1" });
  assert.deepEqual(G.parse("57-300 Kłodzko"), { kind: "text", q: "57-300 Kłodzko" });
  assert.deepEqual(G.parse("  "), { kind: "bad", why: "empty" });
  assert.deepEqual(G.parse("Ny"), { kind: "bad", why: "short" });
  assert.deepEqual(G.parse("95.1, 16.6"), { kind: "bad", why: "range" });
  assert.deepEqual(G.parse("50.4, 196.6"), { kind: "bad", why: "range" });
  assert.deepEqual(G.parse("50°70'N 16°E"), { kind: "bad", why: "coords" });
  assert.deepEqual(G.parse("1 2 3"), { kind: "bad", why: "coords" });
});

test("Nominatim requests: Poland first, the page's language, a postal code as postalcode", () => {
  const zip = new URL(G.url({ kind: "zip", zip: "57-300" }, "uk"));
  assert.equal(zip.origin + zip.pathname, "https://nominatim.openstreetmap.org/search");
  assert.equal(zip.searchParams.get("postalcode"), "57-300");
  assert.equal(zip.searchParams.get("countrycodes"), "pl");
  assert.equal(zip.searchParams.get("accept-language"), "uk");
  assert.equal(zip.searchParams.get("format"), "jsonv2");
  const any = new URL(G.url({ kind: "text", q: "Opava" }, "en", false));
  assert.equal(any.searchParams.get("q"), "Opava");
  assert.equal(any.searchParams.get("countrycodes"), null);
  const rev = new URL(G.reverseUrl(50.43, 16.65, "pl"));
  assert.equal(rev.pathname, "/reverse");
  assert.equal(rev.searchParams.get("lat"), "50.43");
});

test("a result: a short name without the postal code and the country, the bounding box as Leaflet bounds", () => {
  const p = G.place({ lat: "50.4435", lon: "16.6569", display_name: "57-300, Kłodzko, powiat kłodzki, województwo dolnośląskie, Polska",
    boundingbox: ["50.3985", "50.4884", "16.5865", "16.7273"] });
  assert.equal(p.name, "Kłodzko, powiat kłodzki, województwo dolnośląskie");
  assert.deepEqual(p.bounds, [[50.3985, 16.5865], [50.4884, 16.7273]]);
  assert.equal(p.lat, 50.4435);
  assert.equal(G.place({ lat: "1", lon: "2", display_name: "Polska" }).bounds, null);
  assert.equal(G.short("Kłodzko, Клодзько, Клодзький повіт, Нижньосілезьке воєводство, Польща"), "Kłodzko, Клодзько, Клодзький повіт");
});

test("search(): Poland first, the whole world only when Poland has nothing, one request a second", async () => {
  const asked = [];
  const answers = [[], [{ lat: "49.94", lon: "17.90", display_name: "Opava, Moravskoslezský kraj, Česko", boundingbox: ["49.9", "50", "17.8", "18"] }]];
  globalThis.fetch = async (u) => { asked.push([u, Date.now()]); return { ok: true, json: async () => answers.shift() }; };
  const res = await G.search({ kind: "text", q: "Opava" }, "pl");
  assert.equal(asked.length, 2);
  assert.match(asked[0][0], /countrycodes=pl/);
  assert.doesNotMatch(asked[1][0], /countrycodes/);
  assert.ok(asked[1][1] - asked[0][1] >= 1000, "Nominatim allows one request a second");
  assert.equal(res[0].name, "Opava, Moravskoslezský kraj");
  delete globalThis.fetch;
});
