#!/usr/bin/env python3
"""alerty-pl live service: polls gov.pl/web/rcb every POLL_SECONDS and pushes each new alert at once to
open pages (Server-Sent Events), Telegram, e-mail and Web Push subscribers.

Runs behind Caddy on the alerty-cao VM (casper-assistant-ai/casper-infra, deploy/alerty-api), under the
prefix /alerty. Settings come from the environment:

  PUBLIC_URL        https://…/alerty, for links in e-mails
  STATE_DIR         SQLite database (subscribers, what was already sent)
  POLL_SECONDS      20
  ADMIN_TOKEN       bearer token of POST /admin/test
  VAPID_PRIVATE     Web Push private key (PEM or base64url), VAPID_PUBLIC (base64url, uncompressed point)
  VAPID_SUBJECT     mailto:… of the operator
  TELEGRAM_TOKEN    bot token (optional: no bot, no Telegram channel)
  ACS_CONNECTION    Azure Communication Services connection string, ACS_SENDER DoNotReply@….azurecomm.net
  ALLOWED_ORIGINS   comma-separated origins for CORS
"""
import asyncio
import datetime as dt
import json
import logging
import os
import secrets
import sqlite3
import subprocess
import sys
import threading
import time
from collections import defaultdict, deque
from zoneinfo import ZoneInfo

from aiohttp import ClientSession, ClientTimeout, web

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, HERE)
import core
import rcb  # the site's own parser

log = logging.getLogger("alerty")
TZ = ZoneInfo("Europe/Warsaw")
ENV = os.environ.get
PUBLIC_URL = ENV("PUBLIC_URL", "http://127.0.0.1:8090").rstrip("/")
POLL = max(10, int(ENV("POLL_SECONDS", "20")))
DETAIL_RECHECK = 90       # seconds between re-reads of a recent alert's page (updates, cancellations)
ORIGINS = {o.strip() for o in ENV("ALLOWED_ORIGINS", "https://alerty.klioba.com,https://casper-assistant-ai.github.io").split(",") if o.strip()}
MAX_SSE = 3000
MAX_SUBS = 20000


def now():
    return dt.datetime.now(TZ)


def version():
    try:
        return subprocess.run(["git", "-C", ROOT, "rev-parse", "--short", "HEAD"], capture_output=True,
                              text=True, timeout=5).stdout.strip() or "?"
    except Exception:
        return "?"


# ---------------------------------------------------------------- storage
class DB:
    def __init__(self, path):
        self.c = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.c.execute("pragma journal_mode=wal")
        self.c.executescript("""
        create table if not exists subs(
          id integer primary key, channel text not null, address text not null, data text,
          prefs text not null, token text not null, confirmed integer not null default 0,
          created text not null, unique(channel, address));
        create table if not exists tg_links(code text primary key, prefs text not null, created real not null);
        create table if not exists seen(id text primary key, alert text not null, checked real not null);
        create table if not exists sent(alert text, kind text, n integer, sub integer, at text);
        """)

        self.lock = threading.Lock()

    def q(self, sql, *args):
        with self.lock:
            return self.c.execute(sql, args).fetchall()

    def x(self, sql, args=()):
        with self.lock:
            return self.c.execute(sql, args)

    def subs(self, channel, confirmed=True):
        rows = self.q("select id, address, data, prefs, token from subs where channel=? and confirmed>=?",
                      channel, 1 if confirmed else 0)
        return [{"id": r[0], "address": r[1], "data": r[2], "prefs": json.loads(r[3]), "token": r[4]} for r in rows]

    def add(self, channel, address, prefs, data=None, confirmed=1):
        if self.q("select count(*) from subs")[0][0] >= MAX_SUBS:
            raise web.HTTPServiceUnavailable(text="too many subscribers")
        old = self.q("select token, confirmed from subs where channel=? and address=?", channel, address)
        token = old[0][0] if old else secrets.token_urlsafe(24)
        conf = max(confirmed, old[0][1]) if old else confirmed
        self.x("insert into subs(channel,address,data,prefs,token,confirmed,created) values(?,?,?,?,?,?,?) "
                       "on conflict(channel,address) do update set data=excluded.data, prefs=excluded.prefs, "
                       "confirmed=?", (channel, address, data, json.dumps(prefs), token, conf,
                                        now().isoformat(timespec="seconds"), conf))
        return token, conf

    def remove(self, channel, address):
        return self.x("delete from subs where channel=? and address=?", (channel, address)).rowcount

    def by_token(self, token):
        r = self.q("select id, channel, address, confirmed from subs where token=?", token)
        return r[0] if r else None

    def counts(self):
        return {ch: n for ch, n in self.q("select channel, count(*) from subs where confirmed=1 group by channel")}


# ---------------------------------------------------------------- the service
class Service:
    def __init__(self, state_dir):
        os.makedirs(state_dir, exist_ok=True)
        self.db = DB(os.path.join(state_dir, "alerty.db"))
        self.alerts = {}            # id -> full alert, as in docs/data/alerts.json
        self.checked_at = None
        self.poll_error = None
        self.listeners = set()      # SSE queues
        self.gaz = None
        self.http = None
        self.tg_bot = None          # bot username, from getMe
        self.email_q = asyncio.Queue()
        self.vapid_private = ENV("VAPID_PRIVATE", "")
        self.vapid_public = ENV("VAPID_PUBLIC", "")
        self.version = version()
        self.started = now().isoformat(timespec="seconds")
        self.stats = defaultdict(int)

    # ---------- state
    def load_snapshot(self):
        """Start from the site's last alerts.json so a restart neither forgets nor re-sends."""
        path = os.path.join(ROOT, "docs/data/alerts.json")
        try:
            for a in json.load(open(path, encoding="utf-8")).get("alerts", []):
                self.alerts[a["id"]] = a
        except Exception as e:
            log.warning("no snapshot: %s", e)
        known = {r[0]: json.loads(r[1]) for r in self.db.q("select id, alert from seen")}
        for k, a in known.items():
            if k not in self.alerts or len(a.get("updates") or []) >= len(self.alerts[k].get("updates") or []):
                self.alerts[k] = a
        geo = json.load(open(os.path.join(ROOT, "docs/geo/poland.json"), encoding="utf-8"))
        self.gaz = rcb.Gazetteer(geo)

    def remember(self, a):
        self.alerts[a["id"]] = a
        self.db.x("insert into seen(id, alert, checked) values(?,?,?) on conflict(id) do update set "
                          "alert=excluded.alert, checked=excluded.checked",
                          (a["id"], json.dumps(a, ensure_ascii=False), time.time()))

    def snapshot(self):
        t = now()
        rows = []
        for a in self.alerts.values():
            a = dict(a)
            a["status"], a["started_at"], a["last_at"] = rcb.status(a, t)
            rows.append(a)
        cutoff = (t.date() - dt.timedelta(days=rcb.RECENT_DAYS)).isoformat()
        rows = [a for a in rows if a["date"] >= cutoff or a["status"] in ("active", "planned")]
        rows.sort(key=lambda a: (a["date"], a["last_at"]), reverse=True)
        return rows[:400]

    # ---------- polling gov.pl
    def poll_once(self, first):
        t = now()
        items = rcb.parse_list(rcb.fetch(rcb.LIST_URL.format(page=1)))
        if not items:
            raise RuntimeError("list page 1 has no items: the gov.pl layout may have changed")
        events = []
        checked = {r[0]: r[1] for r in self.db.q("select id, checked from seen")}
        for it in items:
            if not it["title"].lower().startswith(("alert rcb", "komunikat")):
                continue
            old = self.alerts.get(it["slug"])
            recent = (t.date() - dt.date.fromisoformat(it["date"])).days <= 2
            if old and not recent:
                continue
            if old and time.time() - checked.get(it["slug"], 0) < DETAIL_RECHECK:
                continue
            try:
                a = rcb.build_alert(it, rcb.fetch_detail(it["url"]), self.gaz, t)
            except Exception as e:  # one bad page must not stop the others; it is tried again next poll
                log.warning("skip %s: %s", it["slug"], e)
                continue
            a["parser"] = rcb.PARSER_VERSION
            if core.regressed(old, a):
                log.warning("kept %s: %d updates now, %d known", it["slug"], len(a["updates"]),
                            len(old["updates"]))
                continue
            kind = core.diff(old, a)
            self.remember(a)
            if kind and not first:
                events.append((kind, a))
            elif kind:
                log.info("baseline %s (%s)", a["id"], kind)
        self.checked_at = t.isoformat(timespec="seconds")
        return events

    async def poll_loop(self):
        first = not self.db.q("select 1 from seen limit 1")
        while True:
            try:
                events = await asyncio.to_thread(self.poll_once, first)
                first = False
                self.poll_error = None
                for kind, a in reversed(events):
                    log.info("%s alert %s", kind, a["id"])
                    await self.dispatch(a, kind)
            except Exception as e:
                self.poll_error = f"{type(e).__name__}: {e}"[:300]
                log.warning("poll failed: %s", self.poll_error)
            await asyncio.sleep(POLL)

    # ---------- fan-out
    async def dispatch(self, alert, kind, targets=None):
        """Send one alert everywhere. targets (tests only): {"sse": bool, "push": [...], "email": [...],
        "telegram": [...]} restricts delivery to those addresses."""
        self.stats["dispatch_" + kind] += 1
        n = {"sse": 0, "push": 0, "email": 0, "telegram": 0}
        if targets is None or targets.get("sse"):
            ev = json.dumps({"kind": kind, "alert": alert, "checked_at": self.checked_at}, ensure_ascii=False)
            for q in list(self.listeners):
                if q.qsize() < 50:
                    q.put_nowait(ev)
                    n["sse"] += 1

        def chosen(channel):
            subs = [s for s in self.db.subs(channel) if core.matches(s["prefs"], alert)]
            if targets is not None:
                want = {str(x) for x in targets.get(channel) or []}
                subs = [s for s in subs if s["address"] in want]
            return subs

        for s in chosen("telegram"):
            n["telegram"] += await self.send_telegram(s, alert, kind)
        push = chosen("push")
        if push:
            n["push"] += sum(await asyncio.gather(*(asyncio.to_thread(self.send_push, s, alert, kind) for s in push)))
        for s in chosen("email"):
            self.email_q.put_nowait((s, alert, kind))
            n["email"] += 1
        self.db.x("insert into sent(alert, kind, n, at) values(?,?,?,?)",
                          (alert["id"], kind, sum(n.values()), now().isoformat(timespec="seconds")))
        return n

    # ---------- Web Push
    def send_push(self, s, alert, kind):
        if not self.vapid_private:
            return 0
        from pywebpush import WebPushException, webpush
        try:
            webpush(json.loads(s["data"]), core.push_payload(alert, kind), vapid_private_key=self.vapid_private,
                    vapid_claims={"sub": ENV("VAPID_SUBJECT", "mailto:casper.assistant.ai@gmail.com")},
                    ttl=3600, timeout=10, headers={"Urgency": "high"})
            self.stats["push_ok"] += 1
            return 1
        except WebPushException as e:
            code = getattr(e.response, "status_code", None)
            if code in (404, 410):
                self.db.remove("push", s["address"])
            self.stats["push_fail"] += 1
            log.warning("push %s: %s", code, str(e)[:200])
        except Exception as e:
            self.stats["push_fail"] += 1
            log.warning("push: %s", str(e)[:200])
        return 0

    # ---------- Telegram
    def tg_url(self, method):
        return f"https://api.telegram.org/bot{ENV('TELEGRAM_TOKEN')}/{method}"

    async def tg(self, method, **payload):
        async with self.http.post(self.tg_url(method), json=payload, timeout=ClientTimeout(total=40)) as r:
            return r.status, await r.json(content_type=None)

    async def send_telegram(self, s, alert, kind):
        if not ENV("TELEGRAM_TOKEN"):
            return 0
        subject, _, url = core.message(alert, kind)
        text = f"<b>{esc(subject)}</b>\n\n{esc(core.latest_message(alert))}\n\n<a href=\"{esc(url)}\">{esc(alert.get('title', ''))}</a>"
        try:
            st, j = await self.tg("sendMessage", chat_id=int(s["address"]), text=text[:4000], parse_mode="HTML",
                                  disable_web_page_preview=True)
            if st == 403:
                self.db.remove("telegram", s["address"])
            if st == 200:
                self.stats["tg_ok"] += 1
                return 1
            log.warning("telegram %s: %s", st, str(j)[:200])
        except Exception as e:
            log.warning("telegram: %s", e)
        self.stats["tg_fail"] += 1
        return 0

    async def tg_loop(self):
        if not ENV("TELEGRAM_TOKEN"):
            return
        offset = 0
        while True:
            try:
                if not self.tg_bot:
                    st, j = await self.tg("getMe")
                    if st == 200:
                        self.tg_bot = j["result"]["username"]
                        await self.tg("deleteWebhook")
                        await self.tg("setMyCommands", commands=[
                            {"command": "start", "description": "Włącz powiadomienia o Alertach RCB"},
                            {"command": "stop", "description": "Wyłącz powiadomienia"},
                            {"command": "status", "description": "Twoje ustawienia"}])
                st, j = await self.tg("getUpdates", offset=offset, timeout=30, allowed_updates=["message"])
                for u in j.get("result", []) if st == 200 else []:
                    offset = max(offset, u["update_id"] + 1)
                    await self.tg_message(u.get("message") or {})
                if st != 200:
                    await asyncio.sleep(10)
            except Exception as e:
                log.warning("telegram loop: %s", e)
                await asyncio.sleep(10)

    async def tg_message(self, m):
        chat = (m.get("chat") or {})
        if chat.get("type") != "private":
            return
        cid, text = str(chat["id"]), (m.get("text") or "").strip()
        if text.startswith("/start"):
            code = text[6:].strip()
            row = self.db.q("select prefs from tg_links where code=?", code) if code else []
            prefs = core.clean_prefs(json.loads(row[0][0])) if row else core.clean_prefs({})
            self.db.add("telegram", cid, prefs)
            reply = ("Powiadomienia włączone: " + where(prefs) +
                     ". Każdy nowy Alert RCB przyjdzie tutaj w ciągu minuty.\n/stop wyłącza, /status pokazuje ustawienia.\n"
                     "Zmiana obszaru: " + core.SITE + "powiadomienia.html")
        elif text.startswith("/stop"):
            reply = "Powiadomienia wyłączone." if self.db.remove("telegram", cid) else "Nie masz włączonych powiadomień."
        elif text.startswith("/status"):
            s = [x for x in self.db.subs("telegram") if x["address"] == cid]
            reply = ("Powiadomienia: " + where(s[0]["prefs"])) if s else "Powiadomienia wyłączone. /start włącza."
        else:
            reply = "Ten bot wysyła Alerty RCB z " + core.SITE + "\n/start — włącz, /stop — wyłącz, /status — ustawienia."
        await self.tg("sendMessage", chat_id=int(cid), text=reply, disable_web_page_preview=True)

    # ---------- e-mail (Azure Communication Services)
    def mail(self, to, subject, text, html_body):
        from azure.communication.email import EmailClient
        client = EmailClient.from_connection_string(ENV("ACS_CONNECTION"))
        poller = client.begin_send({
            "senderAddress": ENV("ACS_SENDER"),
            "recipients": {"to": [{"address": to}]},
            "content": {"subject": subject, "plainText": text, "html": html_body},
            "headers": {"List-Unsubscribe": f"<{PUBLIC_URL}/email/unsubscribe>"},
        })
        res = poller.result(timeout=60)
        return res.get("status") if isinstance(res, dict) else str(res)

    async def email_loop(self):
        while True:
            s, alert, kind = await self.email_q.get()
            subject, text, url = core.message(alert, kind)
            off = f"{PUBLIC_URL}/email/unsubscribe?t={s['token']}"
            text += f"\n\n—\nalerty-pl, strona nieoficjalna. Wypisz się: {off}"
            body = (f"<h2 style=\"font-family:sans-serif\">{esc(subject)}</h2><p style=\"font-family:sans-serif;font-size:16px\">"
                    f"{esc(core.latest_message(alert))}</p><p><a href=\"{esc(url)}\">{esc(alert.get('title', ''))}</a></p>"
                    f"<p style=\"color:#777;font-size:12px\">alerty-pl, strona nieoficjalna · <a href=\"{esc(off)}\">wypisz się</a></p>")
            await self.send_mail(s["address"], subject, text, body)

    async def send_mail(self, to, subject, text, body):
        if not ENV("ACS_CONNECTION"):
            return False
        for attempt in range(6):
            try:
                st = await asyncio.to_thread(self.mail, to, subject, text, body)
                self.stats["mail_ok"] += 1
                log.info("mail %s: %s", subject[:40], st)
                return True
            except Exception as e:
                wait = 70 if "429" in str(e) or "TooManyRequests" in str(e) else 20
                log.warning("mail attempt %d: %s", attempt + 1, str(e)[:300])
                await asyncio.sleep(wait * (attempt + 1))
        self.stats["mail_fail"] += 1
        return False


def esc(s):
    return (str(s or "")).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def where(prefs):
    vs = prefs.get("voivodeships") or []
    w = "cała Polska" if not vs else "woj. " + ", ".join(core.VOIV[v] for v in vs)
    return w + ("" if prefs.get("drills") else ", bez ćwiczeń")


# ---------------------------------------------------------------- HTTP
RATE = defaultdict(deque)


def limited(request, n=10, per=3600):
    ip = request.headers.get("X-Forwarded-For", request.remote or "?").split(",")[0].strip()
    q, t = RATE[ip + request.path], time.time()
    while q and t - q[0] > per:
        q.popleft()
    if len(q) >= n:
        raise web.HTTPTooManyRequests(text="slow down")
    q.append(t)


@web.middleware
async def cors(request, handler):
    origin = request.headers.get("Origin", "")
    if request.method == "OPTIONS":
        resp = web.Response(status=204)
    else:
        try:
            resp = await handler(request)
        except web.HTTPException as e:
            resp = e
    if origin in ORIGINS:
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        resp.headers["Vary"] = "Origin"
    return resp


async def body(request):
    if request.content_length and request.content_length > 8192:
        raise web.HTTPRequestEntityTooLarge(max_size=8192, actual_size=request.content_length)
    try:
        return await request.json()
    except Exception:
        raise web.HTTPBadRequest(text="JSON expected") from None


def page(title, text):
    return web.Response(content_type="text/html", text=(
        "<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>"
        f"<title>{esc(title)}</title><body style='font-family:system-ui;max-width:36em;margin:3em auto;padding:0 1em'>"
        f"<h1>{esc(title)}</h1><p>{esc(text)}</p><p><a href='{core.SITE}'>Alerty RCB — mapa</a></p>"))


def routes(svc):
    r = web.RouteTableDef()

    @r.get("/health")
    async def health(_):
        return web.json_response({"ok": svc.poll_error is None and svc.checked_at is not None,
                                  "checked_at": svc.checked_at, "poll_error": svc.poll_error,
                                  "poll_seconds": POLL, "version": svc.version, "started": svc.started,
                                  "listeners": len(svc.listeners), "subscribers": svc.db.counts(),
                                  "stats": svc.stats})

    @r.get("/config")
    async def config(_):
        return web.json_response({"vapid_public_key": svc.vapid_public or None, "telegram_bot": svc.tg_bot,
                                  "email": bool(ENV("ACS_CONNECTION")), "poll_seconds": POLL})

    @r.get("/alerts")
    async def alerts(_):
        rows = svc.snapshot()
        return web.json_response({"source": rcb.BASE + "/web/rcb/komunikaty", "parser": rcb.PARSER_VERSION,
                                  "alerts": rows, "meta": {"checked_at": svc.checked_at, "count": len(rows),
                                  "active": sum(a["status"] == "active" for a in rows), "live": True}},
                                 dumps=lambda o: json.dumps(o, ensure_ascii=False))

    @r.get("/events")
    async def events(request):
        if len(svc.listeners) >= MAX_SSE:
            raise web.HTTPServiceUnavailable(text="busy")
        resp = web.StreamResponse(headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache",
                                           "X-Accel-Buffering": "no"})
        origin = request.headers.get("Origin", "")
        if origin in ORIGINS:
            resp.headers["Access-Control-Allow-Origin"] = origin
        await resp.prepare(request)
        q = asyncio.Queue()
        svc.listeners.add(q)
        try:
            await resp.write(f"retry: 5000\nevent: hello\ndata: {json.dumps({'checked_at': svc.checked_at})}\n\n".encode())
            while True:
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=25)
                    if ev is None:
                        break
                    await resp.write(f"event: alert\ndata: {ev}\n\n".encode())
                except TimeoutError:
                    await resp.write(f"event: ping\ndata: {json.dumps({'checked_at': svc.checked_at})}\n\n".encode())
        except (ConnectionResetError, asyncio.CancelledError):
            pass
        finally:
            svc.listeners.discard(q)
        return resp

    @r.post("/push/subscribe")
    async def push_sub(request):
        limited(request, 30)
        j = await body(request)
        sub = j.get("subscription") or {}
        ep = sub.get("endpoint", "")
        keys = sub.get("keys") or {}
        if not (isinstance(ep, str) and ep.startswith("https://") and len(ep) < 1000 and keys.get("p256dh") and keys.get("auth")):
            raise web.HTTPBadRequest(text="bad subscription")
        clean = {"endpoint": ep, "keys": {"p256dh": str(keys["p256dh"])[:200], "auth": str(keys["auth"])[:100]}}
        svc.db.add("push", ep, core.clean_prefs(j.get("prefs")), json.dumps(clean))
        return web.json_response({"ok": True})

    @r.post("/push/unsubscribe")
    async def push_unsub(request):
        j = await body(request)
        return web.json_response({"ok": bool(svc.db.remove("push", str(j.get("endpoint", ""))))})

    @r.post("/telegram/link")
    async def tg_link(request):
        limited(request, 30)
        if not svc.tg_bot:
            raise web.HTTPServiceUnavailable(text="telegram not configured")
        j = await body(request)
        code = secrets.token_urlsafe(12)
        svc.db.x("insert into tg_links values(?,?,?)", (code, json.dumps(core.clean_prefs(j.get("prefs"))), time.time()))
        svc.db.x("delete from tg_links where created < ?", (time.time() - 86400,))
        return web.json_response({"url": f"https://t.me/{svc.tg_bot}?start={code}"})

    @r.post("/email/subscribe")
    async def email_sub(request):
        limited(request, 5)
        if not ENV("ACS_CONNECTION"):
            raise web.HTTPServiceUnavailable(text="e-mail not configured")
        j = await body(request)
        addr = str(j.get("email", "")).strip().lower()
        if not core.valid_email(addr):
            raise web.HTTPBadRequest(text="bad e-mail")
        prefs = core.clean_prefs(j.get("prefs"))
        token, confirmed = svc.db.add("email", addr, prefs, confirmed=0)
        if confirmed:
            return web.json_response({"ok": True, "confirmed": True})
        link = f"{PUBLIC_URL}/email/confirm?t={token}"
        asyncio.create_task(svc.send_mail(
            addr, "Potwierdź powiadomienia Alerty RCB",
            f"Ktoś (pewnie Ty) zapisał ten adres na powiadomienia o Alertach RCB ({where(prefs)}).\n"
            f"Potwierdź: {link}\n\nJeśli to nie Ty, zignoruj ten list.",
            f"<p style='font-family:sans-serif'>Ktoś (pewnie Ty) zapisał ten adres na powiadomienia o Alertach RCB "
            f"({esc(where(prefs))}).</p><p><a href='{esc(link)}'>Potwierdź powiadomienia</a></p>"
            f"<p style='color:#777;font-size:12px'>Jeśli to nie Ty, zignoruj ten list.</p>"))
        return web.json_response({"ok": True, "confirmed": False})

    @r.get("/email/confirm")
    async def email_confirm(request):
        row = svc.db.by_token(request.query.get("t", ""))
        if not row or row[1] != "email":
            return page("Link nieważny", "Ten link potwierdzenia nie działa. Zapisz się jeszcze raz na stronie.")
        svc.db.x("update subs set confirmed=1 where id=?", (row[0],))
        return page("Powiadomienia włączone", f"Alerty RCB będą przychodzić na {row[2]}. Każdy list ma link do wypisania.")

    @r.get("/email/unsubscribe")
    async def email_unsub(request):
        row = svc.db.by_token(request.query.get("t", ""))
        if row and row[1] == "email":
            svc.db.remove("email", row[2])
            return page("Wypisano", f"Adres {row[2]} nie dostanie już powiadomień.")
        return page("Wypisano", "Tego adresu nie ma na liście.")

    @r.post("/admin/test")
    async def admin_test(request):
        tok = ENV("ADMIN_TOKEN", "")
        if not tok or not secrets.compare_digest(request.headers.get("Authorization", ""), "Bearer " + tok):
            raise web.HTTPUnauthorized()
        j = await body(request)
        alert = core.test_alert(now().isoformat(timespec="seconds"))
        targets = None if j.get("all") else {k: j.get(k) for k in ("sse", "push", "email", "telegram")}
        n = await svc.dispatch(alert, "test", targets)
        return web.json_response({"sent": n, "alert": alert["id"], "subscribers": svc.db.counts()})

    return r


async def make_app():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    svc = Service(ENV("STATE_DIR", os.path.join(ROOT, ".state")))
    svc.load_snapshot()
    app = web.Application(middlewares=[cors], client_max_size=16384)
    app.add_routes(routes(svc))
    app["svc"] = svc

    async def start(app):
        svc.http = ClientSession()
        app["tasks"] = [asyncio.create_task(c) for c in (svc.poll_loop(), svc.tg_loop(), svc.email_loop())]

    async def stop(app):
        for t in app["tasks"]:
            t.cancel()
        for q in list(svc.listeners):
            q.put_nowait(None)
        await svc.http.close()

    app.on_startup.append(start)
    app.on_cleanup.append(stop)
    return app


if __name__ == "__main__":
    web.run_app(make_app(), host=ENV("HOST", "127.0.0.1"), port=int(ENV("PORT", "8090")), access_log=None,
                shutdown_timeout=3)
