#!/usr/bin/env python3
"""Fetch RCB komunikaty from gov.pl and write docs/data/alerts.json.

Standard library only. The parser is pure (parse_list, parse_detail, build_alert) so the tests
run on saved HTML in tests/fixtures without the network.

Usage:
  rcb.py update [--pages N] [--out docs/data]   fetch, parse, write alerts.json + unmatched.json
  rcb.py parse FILE.html                        print the parsed detail page (debugging)
"""
import argparse
import datetime as dt
import html
import json
import os
import re
import sys
import time
import urllib.request
from zoneinfo import ZoneInfo

BASE = "https://www.gov.pl"
LIST_URL = BASE + "/web/rcb/komunikaty?page={page}&size=10"
TZ = ZoneInfo("Europe/Warsaw")
UA = "alerty-pl/1.0 (+https://github.com/casper-assistant-ai/alerty-pl)"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# voivodeship id -> stem that matches every grammatical case ("lubelskie", "lubelskiego", ...)
VOIVODESHIPS = {
    "dolnoslaskie": "dolnośląsk", "kujawsko-pomorskie": "kujawsko-pomorsk",
    "lubelskie": "lubelsk", "lubuskie": "lubusk", "lodzkie": "łódzk",
    "malopolskie": "małopolsk", "mazowieckie": "mazowieck", "opolskie": "opolsk",
    "podkarpackie": "podkarpack", "podlaskie": "podlask", "pomorskie": "pomorsk",
    "slaskie": "śląsk", "swietokrzyskie": "świętokrzysk",
    "warminsko-mazurskie": "warmińsko-mazursk", "wielkopolskie": "wielkopolsk",
    "zachodniopomorskie": "zachodniopomorsk",
}
ENDINGS = r"(?:ie|iego|iem|im|a|iej|ich|ą)"
NOT_WORD_BEFORE = r"(?<![\w-])"
NOT_WORD_AFTER = r"(?![\w-])"
# city names that contain a voivodeship stem: Biała Podlaska, Ruda Śląska, Piekary Śląskie
CITY_GUARD = r"(?<!Biała )(?<!Białej )(?<!Ruda )(?<!Rudzie )(?<!Rudy )(?<!Piekary )(?<!Piekarach )"

# towns (any case) that are not powiat names -> powiat id; matched capitalised, whole word
TOWNS = {
    r"Warszaw(?:a|ie|y|ę|ą)": "mazowieckie/warszawa",
    r"Marki|Markach": "mazowieckie/wolominski",
    r"Zielonk(?:a|i|ę|ą|ie)": "mazowieckie/wolominski",
    r"Kobyłk(?:a|i|ę|ą|ie)": "mazowieckie/wolominski",
    r"Wołomin(?:ie|a|owi|em)?": "mazowieckie/wolominski",
    r"Legionow(?:o|a|ie|em)": "mazowieckie/legionowski",
}

CATEGORIES = [
    ("air", r"atak\w* z powietrza|zagrożeni\w* z powietrza|atak\w* powietrzn|obron\w* powietrzn|dron"),
    ("drill", r"trening|ćwiczeni|test\w* syren|próbn"),
    ("water", r"wod\w* niezdatn|nie nadaje się do (?:celów )?spożyc|wodociąg"),
    ("ordnance", r"niewybuch|niewypał|ewakuacj"),
    ("weather", r"burz|wiatr|upał|opad|powodzi|powódź|śnieg|oblodzen|mróz|zawiej|smog|meteo|ulew|przymroz"),
    ("fire", r"pożar"),
    ("chemical", r"chemiczn|skażen|substancj"),
]
ENDED = r"odwołan\w*|zakończył\w*|zakończon\w*|brak zagrożenia|nadaje się do spożycia|przywrócon\w*|zniesion\w*"
# how long an alert counts as current after its last update, by category (hours)
TTL = {"air": 12, "drill": 12, "water": 168, "ordnance": 24, "weather": 24, "fire": 24,
       "chemical": 48, "other": 24}


def fetch(url, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "pl"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:  # network trouble: retry, then give up loudly
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"fetch failed: {url}: {last}")


def text(fragment):
    t = re.sub(r"<br\s*/?>|</p>|</li>|</h\d>", "\n", fragment, flags=re.I)
    t = html.unescape(re.sub(r"<[^>]+>", " ", t))
    t = t.replace("\xa0", " ")
    return "\n".join(re.sub(r"[ \t]+", " ", line).strip() for line in t.splitlines() if line.strip())


def parse_list(page_html):
    """Items of one komunikaty list page: slug, url, title, date (ISO), intro."""
    items = []
    for m in re.finditer(
            r'<span class="date">\s*(\d{2})\.(\d{2})\.(\d{4})\s*</span>.*?'
            r'<div class="title">\s*<a href="(/web/rcb/[^"]+)">(.*?)</a>\s*</div>\s*'
            r'(?:<div class="intro">(.*?)</div>)?', page_html, re.S):
        d, mo, y, href, title, intro = m.groups()
        items.append({
            "slug": href.rsplit("/", 1)[-1], "url": BASE + href, "title": text(title),
            "date": f"{y}-{mo}-{d}", "intro": text(intro or ""),
        })
    return items


def article_text(page_html):
    m = re.search(r'<article[^>]*>(.*?)</article>', page_html, re.S)
    body = m.group(1) if m else page_html
    body = re.sub(r"<(script|style|nav|picture)[^>]*>.*?</\1>", " ", body, flags=re.S | re.I)
    return text(body)


def category(title, body):
    t = (title + " " + body[:400]).lower()
    for cat, rx in CATEGORIES:
        if re.search(rx, t):
            return cat
    return "other"


def split_updates(body):
    """[(time 'HH:MM' or None, chunk)] in page order. The page starts with the first message,
    then 'Aktualizacja - g. HH:MM' blocks, usually newest first."""
    parts = re.split(r"(?:Aktualizacja\s*[-–—]?\s*(?:g(?:odz)?\.?\s*)?|^|\n|-{3,}\s*)(\d{1,2}[:.]\d{2})(?=\s*(?:\n|„|\"|$))",
                     body)
    out = [(None, parts[0])]
    for i in range(1, len(parts) - 1, 2):
        out.append((parts[i].replace(".", ":").zfill(5), parts[i + 1]))
    return [(t, c.strip(" -–—\n")) for t, c in out if c.strip(" -–—\n")]


def quotes(chunk):
    return [re.sub(r"\s+", " ", q).strip() for q in re.findall(r"[„\"“](.+?)[”\"“]", chunk, re.S)]


class Gazetteer:
    def __init__(self, geo):
        self.powiaty = geo["powiaty"]
        self.by_v = {}
        for p in self.powiaty:
            self.by_v.setdefault(p["voivodeship"], []).append(p)
        self.patterns = {}
        for p in self.powiaty:
            n = p["name"]
            if p["city"]:
                rx = re.escape(n)
            else:  # "ząbkowicki" matches ząbkowicki/ząbkowickiego/ząbkowickim; "-y" names too
                stem = re.sub(r"(ki|ski|cki|dzki|ny|ty|wy)$", lambda m: m.group(0)[:-1], n)
                rx = re.escape(stem) + r"(?:i|iego|im|y|ego|ym)"
            self.patterns[p["id"]] = re.compile(NOT_WORD_BEFORE + rx + NOT_WORD_AFTER)

    def voivodeships(self, s):
        hits = []
        for vid, stem in VOIVODESHIPS.items():
            for m in re.finditer(CITY_GUARD + NOT_WORD_BEFORE + re.escape(stem) + ENDINGS + NOT_WORD_AFTER, s, re.I):
                hits.append((m.start(), vid))
        return sorted(hits)

    def regions(self, s):
        """Voivodeships and powiaty named in a region sentence. A powiat named in a list goes to
        the nearest voivodeship named before it (or after it, for 'powiatu X (woj. Y)')."""
        vh = self.voivodeships(s)
        vids = [v for _, v in vh]
        cands = [p for v in dict.fromkeys(vids) for p in self.by_v[v]] if vids else self.powiaty
        found = {}
        for p in cands:
            for m in self.patterns[p["id"]].finditer(s):
                if not p["city"] and not re.search(r"pow|powiat", s[max(0, m.start() - 400):m.start()], re.I):
                    continue  # an adjective outside a powiat list ("opolski" in a street name)
                prev = [pos for pos, v in vh if v == p["voivodeship"] and pos <= m.start()]
                nxt = [pos for pos, v in vh if v == p["voivodeship"] and pos > m.start()]
                dist = (m.start() - prev[-1]) if prev else ((nxt[0] - m.start()) + 10_000 if nxt else 20_000)
                key = p["name"] + "@" + str(m.start())
                if key not in found or dist < found[key][0]:
                    found[key] = (dist, p["id"])
        pw = {pid for _, pid in found.values()}
        for rx, pid in TOWNS.items():
            if re.search(NOT_WORD_BEFORE + r"(?:" + rx + r")" + NOT_WORD_AFTER, s):
                pw.add(pid)
        pw = sorted(pw)
        vs = sorted(set(vids) | {pid.split("/")[0] for pid in pw})
        # a whole voivodeship is alerted when it is named without a powiat list
        whole = [v for v in vs if not any(pid.startswith(v + "/") for pid in pw)]
        return {"voivodeships": vs, "powiaty": pw, "whole": whole}


def region_sentences(chunk):
    out = re.findall(r"(?:został\w* wysłan\w*|wysłan\w*|na terenie|dotyczy|w miejscowości|w gminie|gmin\w)"
                     r"[^„\"”]*?(?=\n\s*[-]{3,}|Aktualizacja|$)", chunk, re.S)
    return " ".join(out) if out else chunk


def parse_detail(page_html, gaz, title="", date=None):
    body = article_text(page_html)
    if not title:
        m = re.search(r"<h2[^>]*>(.*?)</h2>", page_html, re.S)
        title = text(m.group(1)) if m else ""
    if date is None:
        m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", body)
        date = f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None
    body = body.replace(title, "", 1) if title else body
    body = re.sub(r"^\s*\d{2}\.\d{2}\.\d{4}\s*", "", body)
    updates, all_regions = [], {"voivodeships": set(), "powiaty": set(), "whole": set()}
    for t, chunk in split_updates(body):
        rg = gaz.regions(region_sentences(chunk))
        msgs = quotes(chunk) or [chunk.split("\n")[0][:500]]
        ended = any(re.search(ENDED, q, re.I) for q in msgs)
        updates.append({"time": t, "message": msgs[0], "ended": ended,
                        "regions": rg, "region_text": region_sentences(chunk)[:600]})
        for k in all_regions:
            all_regions[k] |= set(rg[k])
    # newest first: timed updates by time, the untimed first message last
    timed = sorted((u for u in updates if u["time"]), key=lambda u: u["time"], reverse=True)
    untimed = [u for u in updates if not u["time"]]
    updates = timed + untimed
    return {"title": title, "date": date, "category": category(title, body), "updates": updates,
            "regions": {k: sorted(v) for k, v in all_regions.items()}}


def status(alert, now):
    """active / ended / expired, with started_at and last_at in ISO time (Warsaw)."""
    day = dt.date.fromisoformat(alert["date"])
    times = sorted(u["time"] for u in alert["updates"] if u["time"])

    def at(hhmm):
        h, m = map(int, hhmm.split(":"))
        return dt.datetime.combine(day, dt.time(min(h, 23), min(m, 59)), TZ)

    start = at(times[0]) if times else dt.datetime.combine(day, dt.time(0, 0), TZ)
    last = at(times[-1]) if times else start
    m = re.search(r"w godz\.?\s*(\d{1,2})[:.](\d{2})\s*[-–]\s*(\d{1,2})[:.](\d{2})", json.dumps(alert, ensure_ascii=False))
    end_planned = None
    if m and alert["category"] == "drill":
        start = dt.datetime.combine(day, dt.time(int(m.group(1)), int(m.group(2))), TZ)
        end_planned = dt.datetime.combine(day, dt.time(int(m.group(3)), int(m.group(4))), TZ)
    latest = alert["updates"][0] if alert["updates"] else {"ended": False}
    if latest["ended"]:
        st = "ended"
    elif end_planned:
        st = "active" if start <= now <= end_planned else ("planned" if now < start else "ended")
    elif now - last > dt.timedelta(hours=TTL[alert["category"]]):
        st = "expired"
    else:
        st = "active"
    return st, start.isoformat(), last.isoformat()


def build_alert(item, detail, gaz, now):
    a = parse_detail(detail, gaz, title=item["title"], date=item["date"])
    a.update({"id": item["slug"], "url": item["url"], "intro": item["intro"]})
    a["status"], a["started_at"], a["last_at"] = status(a, now)
    return a


def update(pages, out_dir):
    geo = json.load(open(os.path.join(ROOT, "docs/geo/poland.json"), encoding="utf-8"))
    gaz = Gazetteer(geo)
    path = os.path.join(out_dir, "alerts.json")
    old = {}
    if os.path.exists(path):
        old = {a["id"]: a for a in json.load(open(path, encoding="utf-8")).get("alerts", [])}
    now = dt.datetime.now(TZ)
    items = []
    for page in range(1, pages + 1):
        got = parse_list(fetch(LIST_URL.format(page=page)))
        if not got:
            if page == 1:
                raise RuntimeError("list page 1 has no items: the gov.pl layout may have changed")
            break
        items += got
    alerts, unmatched = [], []
    for it in items:
        if not it["title"].lower().startswith(("alert rcb", "komunikat")):
            continue
        prev = old.get(it["slug"])
        recent = (now.date() - dt.date.fromisoformat(it["date"])).days <= 2
        if prev and not recent and prev.get("parser") == PARSER_VERSION:
            a = prev
            a["status"], a["started_at"], a["last_at"] = status(a, now)
        else:
            a = build_alert(it, fetch(it["url"]), gaz, now)
            a["parser"] = PARSER_VERSION
        alerts.append(a)
        if a["category"] != "other" and not a["regions"]["voivodeships"] and "cała polska" not in json.dumps(a, ensure_ascii=False).lower():
            unmatched.append({"id": a["id"], "title": a["title"], "url": a["url"],
                              "region_text": [u["region_text"] for u in a["updates"]][:3]})
    # keep older alerts that fell off the fetched pages
    seen = {a["id"] for a in alerts}
    for a in old.values():
        if a["id"] not in seen:
            a["status"], a["started_at"], a["last_at"] = status(a, now)
            alerts.append(a)
    alerts.sort(key=lambda a: (a["date"], a["last_at"]), reverse=True)
    alerts = alerts[:400]
    os.makedirs(out_dir, exist_ok=True)
    data = {"source": BASE + "/web/rcb/komunikaty", "parser": PARSER_VERSION, "alerts": alerts}
    write_if_changed(path, data)
    write_if_changed(os.path.join(out_dir, "unmatched.json"), {"items": unmatched})
    meta = {"checked_at": now.isoformat(timespec="seconds"), "count": len(alerts),
            "active": sum(a["status"] == "active" for a in alerts)}
    with open(os.path.join(out_dir, "meta.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=1)
    print(json.dumps(meta, ensure_ascii=False))


def write_if_changed(path, data):
    new = json.dumps(data, ensure_ascii=False, indent=1) + "\n"
    if os.path.exists(path) and open(path, encoding="utf-8").read() == new:
        return False
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(new)
    return True


PARSER_VERSION = 1


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    u = sub.add_parser("update")
    u.add_argument("--pages", type=int, default=3)
    u.add_argument("--out", default=os.path.join(ROOT, "docs/data"))
    p = sub.add_parser("parse")
    p.add_argument("file")
    a = ap.parse_args()
    if a.cmd == "update":
        update(a.pages, a.out)
    else:
        geo = json.load(open(os.path.join(ROOT, "docs/geo/poland.json"), encoding="utf-8"))
        r = parse_detail(open(a.file, encoding="utf-8").read(), Gazetteer(geo))
        json.dump(r, sys.stdout, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
