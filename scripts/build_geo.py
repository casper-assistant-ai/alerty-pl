#!/usr/bin/env python3
"""Build docs/geo/poland.json (SVG paths of voivodeships and powiaty plus the gazetteer) and,
with a fourth argument, docs/geo/poland.geojson (the same shapes and ids in WGS84 for the
zoomable map).

Input: GeoJSON from github.com/ppatrzyk/polska-geojson (MIT), files given on the command line.
Output: projected SVG path strings (simple equirectangular with cos(lat) correction, fine for
Poland) and, for each powiat, the voivodeship that holds its centroid.

Usage: build_geo.py wojewodztwa-min.geojson powiaty-min.geojson docs/geo/poland.json [docs/geo/poland.geojson]
"""
import json
import math
import sys

W, H = 1000, 940
LAT0 = 52.0
K = math.cos(math.radians(LAT0))


def rings(geom):
    if geom["type"] == "Polygon":
        return [geom["coordinates"][0]] + geom["coordinates"][1:]
    out = []
    for poly in geom["coordinates"]:
        out.extend(poly)
    return out


def bbox(features):
    xs, ys = [], []
    for f in features:
        for r in rings(f["geometry"]):
            for lon, lat in r:
                xs.append(lon * K)
                ys.append(lat)
    return min(xs), min(ys), max(xs), max(ys)


def projector(features):
    x0, y0, x1, y1 = bbox(features)
    s = min((W - 20) / (x1 - x0), (H - 20) / (y1 - y0))
    ox = (W - (x1 - x0) * s) / 2
    oy = (H - (y1 - y0) * s) / 2

    def p(lon, lat):
        return round(ox + (lon * K - x0) * s, 1), round(oy + (y1 - lat) * s, 1)

    return p


def path(geom, p):
    parts = []
    for r in rings(geom):
        pts = [p(lon, lat) for lon, lat in r]
        parts.append("M" + "L".join(f"{x} {y}" for x, y in pts) + "Z")
    return "".join(parts)


def centroid(geom):
    r = max(rings(geom), key=len)
    a = cx = cy = 0.0
    for (x1, y1), (x2, y2) in zip(r, r[1:] + r[:1], strict=True):
        c = x1 * y2 - x2 * y1
        a += c
        cx += (x1 + x2) * c
        cy += (y1 + y2) * c
    a /= 2
    return (cx / (6 * a), cy / (6 * a)) if a else tuple(r[0])


def inside(pt, geom):
    x, y = pt
    hit = False
    for r in rings(geom):
        for (x1, y1), (x2, y2) in zip(r, r[1:] + r[:1], strict=True):
            if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
                hit = not hit
    return hit


def slug(s):
    tr = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ ", "acelnoszzACELNOSZZ-")
    return s.translate(tr).lower()


def rounded(geom, nd=3):
    """Coordinates to ~100 m: enough for powiat borders, a third of the size."""
    def r(c):
        return [round(c[0], nd), round(c[1], nd)] if isinstance(c[0], (int, float)) else [r(x) for x in c]
    return {"type": geom["type"], "coordinates": r(geom["coordinates"])}


def geojson(out, woj, pw, file):
    feats = []
    by_name = {f["properties"]["nazwa"]: f for f in woj}
    for v in out["voivodeships"]:
        feats.append({"type": "Feature", "properties": {"kind": "woj", "id": v["id"], "name": v["name"]},
                      "geometry": rounded(by_name[v["name"]]["geometry"])})
    for p, f in zip(out["powiaty"], sorted(pw, key=lambda f: f["properties"]["nazwa"]), strict=True):
        feats.append({"type": "Feature", "properties": {"kind": "pow", "id": p["id"], "name": p["name"],
                      "v": p["voivodeship"], "city": p["city"]}, "geometry": rounded(f["geometry"])})
    with open(file, "w", encoding="utf-8") as fh:
        json.dump({"type": "FeatureCollection", "source": out["source"], "features": feats}, fh,
                  ensure_ascii=False, separators=(",", ":"))
    print(f"{len(feats)} features -> {file}")


def main(woj_file, pow_file, out_file, geojson_file=None):
    woj = json.load(open(woj_file, encoding="utf-8"))["features"]
    pw = json.load(open(pow_file, encoding="utf-8"))["features"]
    p = projector(woj)
    out = {"width": W, "height": H, "source": "github.com/ppatrzyk/polska-geojson (MIT)",
           "voivodeships": [], "powiaty": []}
    for f in sorted(woj, key=lambda f: f["properties"]["nazwa"]):
        name = f["properties"]["nazwa"]
        c = p(*centroid(f["geometry"]))
        out["voivodeships"].append({"id": slug(name), "name": name, "d": path(f["geometry"], p),
                                    "cx": c[0], "cy": c[1]})
    for f in sorted(pw, key=lambda f: f["properties"]["nazwa"]):
        name = f["properties"]["nazwa"].removeprefix("powiat ").strip()
        cen = centroid(f["geometry"])
        v = next((w for w in woj if inside(cen, w["geometry"])), None)
        if v is None:  # centroid on a border: take the nearest voivodeship centroid
            v = min(woj, key=lambda w: math.dist(cen, centroid(w["geometry"])))
        vname = v["properties"]["nazwa"]
        out["powiaty"].append({"id": slug(vname) + "/" + slug(name), "name": name,
                               "voivodeship": slug(vname), "city": name[:1].isupper(),
                               "d": path(f["geometry"], p)})
    with open(out_file, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, separators=(",", ":"))
    print(f"{len(out['voivodeships'])} voivodeships, {len(out['powiaty'])} powiaty -> {out_file}")
    if geojson_file:
        geojson(out, woj, pw, geojson_file)


if __name__ == "__main__":
    main(*sys.argv[1:5])
