#!/usr/bin/env python3
"""Fetch RCB komunikaty from gov.pl and write docs/data/alerts.json.

Standard library only. The parser is pure (parse_list, parse_detail, build_alert) so the tests
run on saved HTML in tests/fixtures without the network.

Usage:
  rcb.py update [--pages N] [--out docs/data]   fetch, parse, write alerts.json + unmatched.json
                                                and add every alert to archive.json (the history)
  rcb.py update --pages 120 --keep-going        one-off backfill of the whole komunikaty archive
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
    r"Zielonk(?:a|i|ę|ą|ie)|Zielonce": "mazowieckie/wolominski",
    r"Kobyłk(?:a|i|ę|ą|ie)|Kobyłce": "mazowieckie/wolominski",
    r"Wołomin(?:ie|a|owi|em)?": "mazowieckie/wolominski",
    r"Legionow(?:o|a|ie|em)": "mazowieckie/legionowski",
}

CATEGORIES = [
    ("air", r"atak\w* z powietrza|zagrożeni\w* z powietrza"
            r"|atak\w* powietrzn|obron\w* powietrzn|dron"),
    ("drill", r"trening|ćwiczeni|test\w* syren|próbn"),
    ("water", r"wod\w* niezdatn|nie nadaje się do (?:celów )?spożyc|wodociąg"),
    ("ordnance", r"niewybuch|niewypał|ewakuacj"),
    ("weather", r"burz|wiatr|upał|opad|powodzi|powódź|śnieg|oblodzen|mróz"
                r"|zawiej|smog|meteo|ulew|przymroz"),
    ("fire", r"pożar"),
    ("chemical", r"chemiczn|skażen|substancj"),
]
ENDED = (r"odwołan\w*|zakończył\w*|zakończon\w*|brak zagrożenia|nadaje się do spożycia"
         r"|przywrócon\w*|zniesion\w*")
# how long an alert counts as current after its last update, by category (hours)
TTL = {"air": 12, "drill": 12, "water": 168, "ordnance": 24, "weather": 24, "fire": 24,
       "chemical": 48, "other": 24}


def fetch(url, tries=3):
    last_error = None
    for attempt in range(tries):
        try:
            request = urllib.request.Request(
                url, headers={"User-Agent": UA, "Accept-Language": "pl"})
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.read().decode("utf-8", "replace")
        except Exception as error:  # network trouble: retry, then give up loudly
            last_error = error
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"fetch failed: {url}: {last_error}")


def text(fragment):
    plain = re.sub(r"<br\s*/?>|</p>|</li>|</h\d>", "\n", fragment, flags=re.I)
    plain = html.unescape(re.sub(r"<[^>]+>", " ", plain))
    plain = plain.replace("\xa0", " ")
    return "\n".join(re.sub(r"[ \t]+", " ", line).strip()
                     for line in plain.splitlines() if line.strip())


def parse_list(page_html):
    """Items of one komunikaty list page: slug, url, title, date (ISO), intro."""
    items = []
    for match in re.finditer(
            r'<span class="date">\s*(\d{2})\.(\d{2})\.(\d{4})\s*</span>.*?'
            r'<div class="title">\s*<a href="(/web/rcb/[^"]+)">(.*?)</a>\s*</div>\s*'
            r'(?:<div class="intro">(.*?)</div>)?', page_html, re.S):
        day, month, year, href, title, intro = match.groups()
        items.append({
            "slug": href.rsplit("/", 1)[-1], "url": BASE + href, "title": text(title),
            "date": f"{year}-{month}-{day}", "intro": text(intro or ""),
        })
    return items


def article_text(page_html):
    match = re.search(r'<article[^>]*>(.*?)</article>', page_html, re.S)
    body = match.group(1) if match else page_html
    body = re.sub(r"<(script|style|nav|picture)[^>]*>.*?</\1>", " ", body, flags=re.S | re.I)
    return text(body)


def category(title, body):
    search_text = (title + " " + body[:400]).lower()
    for name, pattern in CATEGORIES:
        if re.search(pattern, search_text):
            return name
    return "other"


def split_updates(body):
    """[(time 'HH:MM' or None, chunk)] in page order. The page starts with the first message,
    then 'Aktualizacja - g. HH:MM' blocks, usually newest first."""
    parts = re.split(r"(?:Aktualizacja\s*[-–—]?\s*(?:g(?:odz)?\.?\s*)?|^|\n|-{3,}\s*)"
                     r"(\d{1,2}[:.]\d{2})(?=\s*(?:\n|„|\"|$))",
                     body)
    chunks = [(None, parts[0])]
    for index in range(1, len(parts) - 1, 2):
        chunks.append((parts[index].replace(".", ":").zfill(5), parts[index + 1]))
    return [(update_time, chunk.strip(" -–—\n"))
            for update_time, chunk in chunks if chunk.strip(" -–—\n")]


def quotes(chunk):
    return [re.sub(r"\s+", " ", quote).strip()
            for quote in re.findall(r"[„\"“](.+?)[”\"“]", chunk, re.S)]


class Gazetteer:
    def __init__(self, geo):
        self.powiaty = geo["powiaty"]
        self.by_voivodeship = {}
        for powiat in self.powiaty:
            self.by_voivodeship.setdefault(powiat["voivodeship"], []).append(powiat)
        self.patterns = {}
        for powiat in self.powiaty:
            name = powiat["name"]
            if powiat["city"]:
                pattern = re.escape(name)
            else:  # "ząbkowicki" matches ząbkowicki/ząbkowickiego/ząbkowickim; "-y" names too
                stem = re.sub(r"(ki|ski|cki|dzki|ny|ty|wy)$",
                              lambda match: match.group(0)[:-1], name)
                pattern = re.escape(stem) + r"(?:i|iego|im|y|ego|ym)"
            self.patterns[powiat["id"]] = re.compile(
                NOT_WORD_BEFORE + pattern + NOT_WORD_AFTER)

    def voivodeships(self, sentence):
        hits = []
        for voivodeship_id, stem in VOIVODESHIPS.items():
            pattern = (CITY_GUARD + NOT_WORD_BEFORE
                       + re.escape(stem) + ENDINGS + NOT_WORD_AFTER)
            for match in re.finditer(pattern, sentence, re.I):
                hits.append((match.start(), voivodeship_id))
        return sorted(hits)

    def regions(self, sentence):
        """Voivodeships and powiaty named in a region sentence. A powiat named in a list goes to
        the nearest voivodeship named before it (or after it, for 'powiatu X (woj. Y)')."""
        voivodeship_hits = self.voivodeships(sentence)
        hit_ids = [voivodeship_id for _, voivodeship_id in voivodeship_hits]
        if hit_ids:
            candidates = [powiat for voivodeship_id in dict.fromkeys(hit_ids)
                          for powiat in self.by_voivodeship[voivodeship_id]]
        else:
            candidates = self.powiaty
        found = {}
        for powiat in candidates:
            for match in self.patterns[powiat["id"]].finditer(sentence):
                context = sentence[max(0, match.start() - 400):match.start()]
                if not powiat["city"] and not re.search(r"pow|powiat", context, re.I):
                    continue  # an adjective outside a powiat list ("opolski" in a street name)
                own_hits = [position for position, voivodeship_id in voivodeship_hits
                            if voivodeship_id == powiat["voivodeship"]]
                before_hits = [position for position in own_hits if position <= match.start()]
                after_hits = [position for position in own_hits if position > match.start()]
                if before_hits:
                    distance = match.start() - before_hits[-1]
                elif after_hits:
                    distance = after_hits[0] - match.start() + 10_000
                else:
                    distance = 20_000
                key = powiat["name"] + "@" + str(match.start())
                if key not in found or distance < found[key][0]:
                    found[key] = (distance, powiat["id"])
        powiat_ids = {powiat_id for _, powiat_id in found.values()}
        for town_pattern, powiat_id in TOWNS.items():
            pattern = NOT_WORD_BEFORE + r"(?:" + town_pattern + r")" + NOT_WORD_AFTER
            if re.search(pattern, sentence):
                powiat_ids.add(powiat_id)
        powiat_ids = sorted(powiat_ids)
        voivodeship_ids = sorted(
            set(hit_ids) | {powiat_id.split("/")[0] for powiat_id in powiat_ids})
        # a whole voivodeship is alerted when it is named without a powiat list
        whole = [voivodeship_id for voivodeship_id in voivodeship_ids
                 if not any(powiat_id.startswith(voivodeship_id + "/")
                            for powiat_id in powiat_ids)]
        return {"voivodeships": voivodeship_ids, "powiaty": powiat_ids, "whole": whole}


def region_sentences(chunk):
    sentences = re.findall(r"(?:został\w* wysłan\w*|wysłan\w*|na terenie|dotyczy|"
                           r"w miejscowości|w gminie|gmin\w)"
                           r"[^„\"”]*?(?=\n\s*[-]{3,}|Aktualizacja|$)", chunk, re.S)
    return " ".join(sentences) if sentences else chunk


def parse_detail(page_html, gazetteer, title="", date=None):
    body = article_text(page_html)
    if not title:
        match = re.search(r"<h2[^>]*>(.*?)</h2>", page_html, re.S)
        title = text(match.group(1)) if match else ""
    if date is None:
        match = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", body)
        date = f"{match.group(3)}-{match.group(2)}-{match.group(1)}" if match else None
    body = body.replace(title, "", 1) if title else body
    body = re.sub(r"^\s*\d{2}\.\d{2}\.\d{4}\s*", "", body)
    updates, all_regions = [], {"voivodeships": set(), "powiaty": set(), "whole": set()}
    for update_time, chunk in split_updates(body):
        regions = gazetteer.regions(region_sentences(chunk))
        messages = quotes(chunk) or [chunk.split("\n")[0][:500]]
        ended = any(re.search(ENDED, message, re.I) for message in messages)
        updates.append({"time": update_time, "message": messages[0], "ended": ended,
                        "regions": regions, "region_text": region_sentences(chunk)[:600]})
        for region_kind in all_regions:
            all_regions[region_kind] |= set(regions[region_kind])
    # newest first: timed updates by time, the untimed first message last
    timed = sorted((update for update in updates if update["time"]),
                   key=lambda update: update["time"], reverse=True)
    untimed = [update for update in updates if not update["time"]]
    updates = timed + untimed
    return {"title": title, "date": date, "category": category(title, body), "updates": updates,
            "regions": {region_kind: sorted(region_ids)
                        for region_kind, region_ids in all_regions.items()}}


def status(alert, now):
    """active / ended / expired, with started_at and last_at in ISO time (Warsaw)."""
    day = dt.date.fromisoformat(alert["date"])
    times = sorted(update["time"] for update in alert["updates"] if update["time"])

    def time_on_day(clock):
        hour, minute = map(int, clock.split(":"))
        return dt.datetime.combine(day, dt.time(min(hour, 23), min(minute, 59)), TZ)

    start = time_on_day(times[0]) if times else dt.datetime.combine(day, dt.time(0, 0), TZ)
    last = time_on_day(times[-1]) if times else start
    alert_json = json.dumps(alert, ensure_ascii=False)
    window = re.search(
        r"w godz\.?\s*(\d{1,2})[:.](\d{2})\s*[-–]\s*(\d{1,2})[:.](\d{2})", alert_json)
    end_planned = None
    if window and alert["category"] == "drill":
        start = dt.datetime.combine(day, dt.time(int(window.group(1)), int(window.group(2))), TZ)
        end_planned = dt.datetime.combine(
            day, dt.time(int(window.group(3)), int(window.group(4))), TZ)
    latest = alert["updates"][0] if alert["updates"] else {"ended": False}
    if latest["ended"]:
        alert_status = "ended"
    elif end_planned:
        alert_status = "active" if start <= now <= end_planned else (
            "planned" if now < start else "ended")
    elif now - last > dt.timedelta(hours=TTL[alert["category"]]):
        alert_status = "expired"
    else:
        alert_status = "active"
    return alert_status, start.isoformat(), last.isoformat()


def build_alert(item, detail, gazetteer, now):
    alert = parse_detail(detail, gazetteer, title=item["title"], date=item["date"])
    alert.update({"id": item["slug"], "url": item["url"], "intro": item["intro"]})
    alert["status"], alert["started_at"], alert["last_at"] = status(alert, now)
    return alert


def compact(alert):
    """The archive record of an alert: what the history and analytics pages need."""
    first = alert["updates"][-1]["message"] if alert["updates"] else alert.get("intro", "")
    return {"id": alert["id"], "url": alert["url"], "title": alert["title"],
            "date": alert["date"], "category": alert["category"], "status": alert["status"],
            "started_at": alert["started_at"], "last_at": alert["last_at"],
            "voivodeships": alert["regions"]["voivodeships"],
            "powiaty": alert["regions"]["powiaty"], "whole": alert["regions"]["whole"],
            "updates": len(alert["updates"]), "message": (first or "")[:400]}


def update_archive(out_dir, alerts):
    """archive.json keeps every alert ever seen, newest first; it is never trimmed."""
    path = os.path.join(out_dir, "archive.json")
    known = {}
    if os.path.exists(path):
        saved = json.load(open(path, encoding="utf-8")).get("alerts", [])
        known = {alert["id"]: alert for alert in saved}
    for alert in alerts:
        known[alert["id"]] = compact(alert)
    rows = sorted(known.values(),
                  key=lambda record: (record["date"], record["started_at"]), reverse=True)
    write_if_changed(path, {"source": BASE + "/web/rcb/komunikaty", "parser": PARSER_VERSION,
                            "count": len(rows), "alerts": rows}, indent=None)
    return len(rows)


def update(pages, out_dir, keep_going=False):
    geo = json.load(open(os.path.join(ROOT, "docs/geo/poland.json"), encoding="utf-8"))
    gazetteer = Gazetteer(geo)
    path = os.path.join(out_dir, "alerts.json")
    cached = {}
    if os.path.exists(path):
        saved = json.load(open(path, encoding="utf-8")).get("alerts", [])
        cached = {alert["id"]: alert for alert in saved}
    now = dt.datetime.now(TZ)
    items = []
    for page in range(1, pages + 1):
        listed = parse_list(fetch(LIST_URL.format(page=page)))
        if not listed:
            if page == 1:
                raise RuntimeError(
                    "list page 1 has no items: the gov.pl layout may have changed")
            break
        items += listed
    alerts, unmatched = [], []
    for item in items:
        if not item["title"].lower().startswith(("alert rcb", "komunikat")):
            continue
        previous = cached.get(item["slug"])
        recent = (now.date() - dt.date.fromisoformat(item["date"])).days <= 2
        if previous and not recent and previous.get("parser") == PARSER_VERSION:
            alert = previous
            alert["status"], alert["started_at"], alert["last_at"] = status(alert, now)
        else:
            try:
                alert = build_alert(item, fetch(item["url"]), gazetteer, now)
            except Exception as error:
                # a backfill skips a broken old page; a normal run fails loudly
                if not keep_going:
                    raise
                print(f"skip {item['url']}: {error}", file=sys.stderr)
                continue
            alert["parser"] = PARSER_VERSION
        alerts.append(alert)
        if (alert["category"] != "other" and not alert["regions"]["voivodeships"]
                and "cała polska" not in json.dumps(alert, ensure_ascii=False).lower()):
            unmatched.append({"id": alert["id"], "title": alert["title"], "url": alert["url"],
                              "region_text": [entry["region_text"]
                                              for entry in alert["updates"]][:3]})
    # keep older alerts that fell off the fetched pages
    seen = {alert["id"] for alert in alerts}
    for alert in cached.values():
        if alert["id"] not in seen:
            alert["status"], alert["started_at"], alert["last_at"] = status(alert, now)
            alerts.append(alert)
    alerts.sort(key=lambda alert: (alert["date"], alert["last_at"]), reverse=True)
    os.makedirs(out_dir, exist_ok=True)
    total = update_archive(out_dir, alerts)
    # the live map needs only recent alerts; the history lives in archive.json
    cutoff = (now.date() - dt.timedelta(days=RECENT_DAYS)).isoformat()
    alerts = [alert for alert in alerts
              if alert["date"] >= cutoff or alert["status"] in ("active", "planned")][:400]
    data = {"source": BASE + "/web/rcb/komunikaty", "parser": PARSER_VERSION, "alerts": alerts}
    write_if_changed(path, data)
    write_if_changed(os.path.join(out_dir, "unmatched.json"), {"items": unmatched})
    meta = {"checked_at": now.isoformat(timespec="seconds"), "count": len(alerts),
            "active": sum(alert["status"] == "active" for alert in alerts), "archive": total}
    with open(os.path.join(out_dir, "meta.json"), "w", encoding="utf-8") as meta_file:
        json.dump(meta, meta_file, ensure_ascii=False, indent=1)
    print(json.dumps(meta, ensure_ascii=False))


def write_if_changed(path, data, indent=1):
    rendered = json.dumps(data, ensure_ascii=False, indent=indent) + "\n"
    if os.path.exists(path) and open(path, encoding="utf-8").read() == rendered:
        return False
    with open(path, "w", encoding="utf-8") as target:
        target.write(rendered)
    return True


PARSER_VERSION = 2  # 2: TOWNS rules for the Warsaw area (komunikat-1811) — re-parse cached alerts
RECENT_DAYS = 60  # alerts.json keeps this many days; archive.json keeps everything


def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="cmd", required=True)
    update_cmd = subparsers.add_parser("update")
    update_cmd.add_argument("--pages", type=int, default=3)
    update_cmd.add_argument("--out", default=os.path.join(ROOT, "docs/data"))
    update_cmd.add_argument("--keep-going", action="store_true",
                            help="skip detail pages that fail (backfill)")
    parse_cmd = subparsers.add_parser("parse")
    parse_cmd.add_argument("file")
    args = parser.parse_args()
    if args.cmd == "update":
        update(args.pages, args.out, args.keep_going)
    else:
        geo = json.load(open(os.path.join(ROOT, "docs/geo/poland.json"), encoding="utf-8"))
        page_html = open(args.file, encoding="utf-8").read()
        detail = parse_detail(page_html, Gazetteer(geo))
        json.dump(detail, sys.stdout, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
