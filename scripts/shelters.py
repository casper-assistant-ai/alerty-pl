#!/usr/bin/env python3
"""Shelter points in Poland (punkty schronienia) for the Schrony page.

Source: the open data set «Punkty schronienia w Polsce» of the State Fire Service headquarters
(KG PSP) on dane.gov.pl (dataset 28058, CC BY 4.0, updated weekly), a CSV published at
gdziesieukryc.pl. Python 3, stdlib only.

  python3 -I scripts/shelters.py update [--src FILE_OR_URL] [--out docs/data/shelters]

The output is split into square cells of CELL degrees, so a phone loads only the cells around the
user and not the whole country:
  index.json         source, update time, count, and per cell [count, mean lat, mean lon]
  t/<row>_<col>.json [[lat, lon, address, gmina, access], ...]; access 0 = round the clock,
                     1 = set hours, 2 = on request
A run that reads far fewer points than the last one (a broken or partial file) writes nothing.
"""
import argparse
import csv
import io
import json
import math
import os
import shutil
import sys
import tempfile
import time
import urllib.request

CSV_URL = "https://gdziesieukryc.pl/PS_XML/punkty_schronienia.csv"
DATASET_API = "https://api.dane.gov.pl/1.4/datasets/28058/resources"
DATASET_PAGE = "https://dane.gov.pl/pl/dataset/28058,punkty-schronienia-w-polsce"
CELL = 0.25
BBOX = (48.9, 55.0, 14.0, 24.2)  # lat min, lat max, lon min, lon max: Poland with a margin
ACCESS = {"całodobowa": 0, "określone godziny": 1, "na żądanie": 2}
MIN_SHARE = 0.7  # refuse a file with fewer than 70% of the points of the last run
UA = "alerty-pl (+https://github.com/casper-assistant-ai/alerty-pl)"


def fetch(url, timeout=120):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def csv_url():
    """The current CSV address from the dane.gov.pl API, or the known one."""
    try:
        data = json.loads(fetch(DATASET_API, 30))
        for res in data.get("data", []):
            a = res.get("attributes", {})
            url = a.get("file_url") or a.get("link") or ""
            if (a.get("format") or "").lower() == "csv" and url.startswith("https://"):
                return url
    except Exception as e:  # noqa: BLE001 - the API is only a hint
        print("dane.gov.pl API:", e, file=sys.stderr)
    return CSV_URL


def cell_of(lat, lon):
    return f"{math.floor(lat / CELL)}_{math.floor(lon / CELL)}"


def parse(text):
    """CSV text -> list of [lat, lon, address, gmina, access]; rows without valid coordinates are skipped."""
    rows, skipped = [], 0
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    need = {"Szerokosc geograficzna", "Dlugosc geograficzna", "Adres"}
    if not need <= set(reader.fieldnames or []):
        raise ValueError(f"unexpected CSV columns: {reader.fieldnames}")
    for r in reader:
        try:
            lat = float((r.get("Szerokosc geograficzna") or "").replace(",", "."))
            lon = float((r.get("Dlugosc geograficzna") or "").replace(",", "."))
        except ValueError:
            skipped += 1
            continue
        if not (BBOX[0] < lat < BBOX[1] and BBOX[2] < lon < BBOX[3]):
            skipped += 1
            continue
        addr = " ".join((r.get("Adres") or "").split())
        gmina = " ".join((r.get("Gmina") or "").split())
        if gmina.lower() in ("nieznana", "brak", "-"):
            gmina = ""
        access = ACCESS.get((r.get("Dostepnosc") or "").strip().lower(), 2)
        rows.append([round(lat, 5), round(lon, 5), addr, gmina, access])
    rows.sort()
    return rows, skipped


def build(rows):
    """rows -> (index cells, {cell: rows})"""
    cells = {}
    for row in rows:
        cells.setdefault(cell_of(row[0], row[1]), []).append(row)
    index = {}
    for key, pts in sorted(cells.items()):
        n = len(pts)
        index[key] = [n, round(sum(p[0] for p in pts) / n, 4), round(sum(p[1] for p in pts) / n, 4)]
    return index, cells


def write(out, rows, skipped, source_url):
    index, cells = build(rows)
    old = os.path.join(out, "index.json")
    if os.path.exists(old):
        with open(old, encoding="utf-8") as f:
            prev = json.load(f)
        if len(rows) < MIN_SHARE * prev.get("count", 0):
            raise SystemExit(f"only {len(rows)} points, the last run had {prev['count']}: not written")
        if prev.get("cells") == index and _same_cells(out, cells):
            print(f"{len(rows)} points, unchanged")
            return False
    tmp = tempfile.mkdtemp(prefix="shelters-", dir=os.path.dirname(os.path.abspath(out)) or ".")
    try:
        os.makedirs(os.path.join(tmp, "t"))
        for key, pts in cells.items():
            with open(os.path.join(tmp, "t", key + ".json"), "w", encoding="utf-8") as f:
                json.dump(pts, f, ensure_ascii=False, separators=(",", ":"))
        meta = {
            "source": "Komenda Główna Państwowej Straży Pożarnej, «Punkty schronienia w Polsce»",
            "source_url": DATASET_PAGE,
            "file_url": source_url,
            "license": "CC BY 4.0",
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "count": len(rows),
            "skipped": skipped,
            "cell": CELL,
            "access": ["całodobowo", "w określonych godzinach", "na żądanie"],
            "cells": index,
        }
        with open(os.path.join(tmp, "index.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, separators=(",", ":"))
        if os.path.exists(out):
            shutil.rmtree(out)
        os.replace(tmp, out)
    finally:
        if os.path.exists(tmp):
            shutil.rmtree(tmp)
    print(f"{len(rows)} points in {len(cells)} cells, {skipped} skipped")
    return True


def _same_cells(out, cells):
    for key, pts in cells.items():
        path = os.path.join(out, "t", key + ".json")
        if not os.path.exists(path):
            return False
        with open(path, encoding="utf-8") as f:
            if json.load(f) != pts:
                return False
    return len(os.listdir(os.path.join(out, "t"))) == len(cells)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    up = sub.add_parser("update", help="download the CSV and rebuild the cells")
    up.add_argument("--src", help="a local CSV file or a URL instead of the dane.gov.pl file")
    up.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "..", "docs", "data", "shelters"))
    a = ap.parse_args(argv)
    src = a.src or csv_url()
    if os.path.exists(src):
        with open(src, encoding="utf-8-sig") as f:
            text = f.read()
    else:
        text = fetch(src).decode("utf-8-sig")
    rows, skipped = parse(text)
    if len(rows) < 1000 and not a.src:
        raise SystemExit(f"only {len(rows)} points read from {src}: not written")
    write(os.path.normpath(a.out), rows, skipped, src if src.startswith("http") else CSV_URL)


if __name__ == "__main__":
    main()
