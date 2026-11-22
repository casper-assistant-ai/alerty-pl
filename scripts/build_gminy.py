#!/usr/bin/env python3
"""Build docs/geo/gminy.json: every gmina of Poland with its TERYT code and the powiat id used in
docs/geo/poland.json, so the parser can name the gminas an alert mentions. Also writes
docs/geo/names.json, the powiat names the pages show under an alert ("pow. zgorzelecki", "Wrocław"),
so they need not load the map shapes.

Source: the State Register of Borders (PRG) of GUGiK, WFS service AdministrativeBoundaries,
layers A02_Granice_powiatow and A03_Granice_gmin (names and TERYT codes only, no shapes).

Usage: build_gminy.py [docs/geo/gminy.json]     (names.json only: build_gminy.py --names)
"""
import json
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WFS = ("https://mapy.geoportal.gov.pl/wss/service/PZGIK/PRG/WFS/AdministrativeBoundaries"
       "?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES=ms:{layer}"
       "&PROPERTYNAME=JPT_KOD_JE,JPT_NAZWA_&COUNT=5000")
# TERYT voivodeship code -> id in poland.json
VOIV = {"02": "dolnoslaskie", "04": "kujawsko-pomorskie", "06": "lubelskie", "08": "lubuskie",
        "10": "lodzkie", "12": "malopolskie", "14": "mazowieckie", "16": "opolskie",
        "18": "podkarpackie", "20": "podlaskie", "22": "pomorskie", "24": "slaskie",
        "26": "swietokrzyskie", "28": "warminsko-mazurskie", "30": "wielkopolskie",
        "32": "zachodniopomorskie"}
# the last digit of a gmina's TERYT code
KIND = {"1": "miejska", "2": "wiejska", "3": "miejsko-wiejska"}
# powiaty renamed after the shapes in poland.json were drawn: PRG name -> poland.json name
RENAMED = {"karkonoski": "jeleniogórski"}  # since 1.01.2021


def features(xml):
    """(code, name) pairs from a WFS GetFeature answer."""
    return re.findall(r"<ms:JPT_KOD_JE>([^<]*)</ms:JPT_KOD_JE>\s*<ms:JPT_NAZWA_>([^<]*)</ms:JPT_NAZWA_>", xml)


def powiat_ids(prg_powiaty, geo_powiaty):
    """TERYT powiat code (4 digits) -> poland.json powiat id, matched by name within the voivodeship."""
    by_name = {(p["voivodeship"], p["name"].lower()): p["id"] for p in geo_powiaty}
    out, missing = {}, []
    for code, name in prg_powiaty:
        v = VOIV[code[:2]]
        n = re.sub(r"^powiat\s+", "", name).lower()
        n = RENAMED.get(n, n)
        pid = by_name.get((v, n))
        if pid:
            out[code] = pid
        else:
            missing.append(f"{code} {name}")
    return out, missing


def build(prg_powiaty, prg_gminy, geo_powiaty):
    ids, missing = powiat_ids(prg_powiaty, geo_powiaty)
    rows = []
    for code, name in prg_gminy:
        pid = ids.get(code[:4])
        if not pid:
            missing.append(f"{code} {name}")
            continue
        rows.append({"teryt": code, "name": name, "powiat": pid, "kind": KIND.get(code[-1], "")})
    rows.sort(key=lambda r: r["teryt"])
    return rows, missing


def names(geo_powiaty):
    """Powiat id -> the label the pages show: a city powiat by its name, others as "pow. <name>"."""
    return {p["id"]: p["name"] if p["city"] else "pow. " + p["name"] for p in geo_powiaty}


def write_names(geo):
    path = os.path.join(ROOT, "docs/geo/names.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"powiaty": names(geo["powiaty"])}, fh, ensure_ascii=False, indent=None, sort_keys=True)
        fh.write("\n")
    return path


def fetch(layer):
    req = urllib.request.Request(WFS.format(layer=layer), headers={"User-Agent": "alerty-pl"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return r.read().decode("utf-8")


def main():
    geo = json.load(open(os.path.join(ROOT, "docs/geo/poland.json"), encoding="utf-8"))
    print("names ->", write_names(geo))
    if sys.argv[1:] == ["--names"]:
        return
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "docs/geo/gminy.json")
    rows, missing = build(features(fetch("A02_Granice_powiatow")), features(fetch("A03_Granice_gmin")),
                          geo["powiaty"])
    if missing:
        sys.exit("no powiat in poland.json for: " + "; ".join(missing[:20]))
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({"source": "PRG (GUGiK), WFS AdministrativeBoundaries, A03_Granice_gmin",
                   "count": len(rows), "gminy": rows}, fh, ensure_ascii=False, indent=None)
        fh.write("\n")
    print(f"{len(rows)} gminy -> {out}")


if __name__ == "__main__":
    main()
