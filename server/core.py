"""Pure logic of the alerty-pl live service: who gets an alert and what the message says.

Standard library only, so the tests run in CI without the service's packages.
"""
import json
import re

CAT = {
    "air": "Zagrożenie z powietrza", "drill": "Ćwiczenia i testy syren", "water": "Woda niezdatna do picia",
    "weather": "Pogoda i powietrze", "ordnance": "Niewybuchy i ewakuacje", "fire": "Pożary",
    "chemical": "Skażenia", "other": "Inne komunikaty",
}
VOIV = {
    "dolnoslaskie": "dolnośląskie", "kujawsko-pomorskie": "kujawsko-pomorskie", "lubelskie": "lubelskie",
    "lubuskie": "lubuskie", "lodzkie": "łódzkie", "malopolskie": "małopolskie", "mazowieckie": "mazowieckie",
    "opolskie": "opolskie", "podkarpackie": "podkarpackie", "podlaskie": "podlaskie", "pomorskie": "pomorskie",
    "slaskie": "śląskie", "swietokrzyskie": "świętokrzyskie", "warminsko-mazurskie": "warmińsko-mazurskie",
    "wielkopolskie": "wielkopolskie", "zachodniopomorskie": "zachodniopomorskie",
}
SITE = "https://alerty.klioba.com/"
EMAIL_RE = re.compile(r"^[^@\s<>\"']{1,64}@[A-Za-z0-9.-]{1,190}\.[A-Za-z]{2,24}$")


def clean_prefs(raw):
    """Subscriber preferences from untrusted JSON: voivodeship ids (empty = all of Poland) and drills on/off."""
    raw = raw if isinstance(raw, dict) else {}
    vs = raw.get("voivodeships") or []
    vs = sorted({v for v in vs if isinstance(v, str) and v in VOIV}) if isinstance(vs, list) else []
    return {"voivodeships": vs, "drills": bool(raw.get("drills", False))}


def valid_email(addr):
    return isinstance(addr, str) and len(addr) <= 254 and bool(EMAIL_RE.match(addr.strip()))


def regions_of(alert):
    r = alert.get("regions") or {}
    return set(r.get("voivodeships") or []), bool(r.get("whole"))


def matches(prefs, alert):
    """Does a subscriber with these preferences want this alert?"""
    if alert.get("test"):
        return True
    if alert.get("category") == "drill" and not prefs.get("drills"):
        return False
    want = set(prefs.get("voivodeships") or [])
    if not want:
        return True
    vs, whole = regions_of(alert)
    if whole:
        return True
    if not vs:  # area not recognised: better one alert too many than one missed
        return True
    return bool(want & vs)


def latest_message(alert):
    ups = alert.get("updates") or []
    if ups and ups[0].get("message"):
        return ups[0]["message"]
    return (alert.get("intro") or "").strip('" ')


def region_line(alert):
    if alert.get("test"):
        return "próba, bez obszaru"
    vs, whole = regions_of(alert)
    if whole:
        return "cała Polska"
    if not vs:
        return "obszar w komunikacie"
    return "woj. " + ", ".join(VOIV.get(v, v) for v in sorted(vs))


def message(alert, kind):
    """(subject, text, url) of a notification. kind: new, update or test."""
    cat = CAT.get(alert.get("category"), CAT["other"])
    head = {"new": "Nowy alert", "update": "Aktualizacja alertu", "test": "TEST"}.get(kind, "Alert")
    if alert.get("status") == "ended" and kind == "update":
        head = "Odwołanie alertu"
    subject = f"{head}: {cat} · {region_line(alert)}"
    body = latest_message(alert)
    if len(body) > 900:
        body = body[:897] + "…"
    url = alert.get("url") or SITE
    text = f"{subject}\n\n{body}\n\n{alert.get('title', '')}\n{url}"
    return subject, text, url


def diff(old, new):
    """Notification kind for a freshly parsed alert against what was known: new, update or None."""
    if old is None:
        return "new"
    if len(new.get("updates") or []) > len(old.get("updates") or []):
        return "update"
    if new.get("status") == "ended" and old.get("status") not in ("ended", "expired"):
        return "update"
    return None


def push_payload(alert, kind):
    subject, _, url = message(alert, kind)
    body = latest_message(alert)
    return json.dumps({"title": subject, "body": body[:240], "url": url, "tag": alert.get("id", "alert"),
                       "kind": kind}, ensure_ascii=False)


def test_alert(now_iso):
    return {
        "id": "test-" + re.sub(r"\D", "", now_iso)[:14], "test": True, "category": "other",
        "title": "Alert testowy alerty-pl", "date": now_iso[:10], "status": "active",
        "started_at": now_iso, "last_at": now_iso, "url": SITE,
        "updates": [{"time": None, "message": "To jest próbne powiadomienie alerty-pl. Nic się nie dzieje.",
                     "ended": False, "regions": {"voivodeships": [], "powiaty": [], "whole": []}}],
        "regions": {"voivodeships": [], "powiaty": [], "whole": []},
    }
