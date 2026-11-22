// Alerty RCB — the notifications page: choose voivodeships, then Telegram, e-mail or Web Push.
// Everything goes to the live service (RCB.API, casper-infra deploy/alerty-api).
"use strict";
const { API, VOIV, $, h, strip } = RCB;

const KEY = "alerty-prefs";
const saved = (() => { try { return JSON.parse(localStorage.getItem(KEY)) || {}; } catch (e) { return {}; } })();

function prefs() {
  const voivodeships = [...document.querySelectorAll("#areas input:checked")].map((i) => i.value);
  const p = { voivodeships, drills: $("#drills").checked };
  localStorage.setItem(KEY, JSON.stringify(p));
  return p;
}

function say(id, text, err = false) {
  const o = $(id);
  o.textContent = text;
  o.classList.toggle("err", err);
}

async function post(path, data) {
  const r = await fetch(API + path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
  if (!r.ok) throw new Error((await r.text()) || r.status);
  return r.json();
}

// VAPID public key (base64url) -> Uint8Array for pushManager.subscribe
function key(b64) {
  const s = atob((b64 + "=".repeat((4 - (b64.length % 4)) % 4)).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(s, (c) => c.charCodeAt(0));
}

async function pushState(cfg) {
  const ok = "serviceWorker" in navigator && "PushManager" in window && cfg.vapid_public_key;
  if (!ok) {
    $("#c-push").setAttribute("aria-disabled", "true");
    $("#push-go").disabled = true;
    say("#push-out", "Ta przeglądarka nie obsługuje powiadomień push (na iPhonie dodaj stronę do ekranu początkowego).");
    return null;
  }
  const reg = await navigator.serviceWorker.register("sw.js");
  const sub = await reg.pushManager.getSubscription();
  $("#push-off").hidden = !sub;
  $("#push-go").textContent = sub ? "Zapisz obszar" : "Włącz";
  if (sub) say("#push-out", "Powiadomienia w tej przeglądarce są włączone.");
  return reg;
}

async function main() {
  strip();
  const want = new Set(saved.voivodeships || []);
  const areas = $("#areas");
  for (const [id, name] of Object.entries(VOIV)) {
    const i = h("input", { type: "checkbox", value: id });
    i.checked = want.has(id);
    areas.append(h("label", { class: "chk" }, i, h("span", { text: name })));
  }
  $("#drills").checked = !!saved.drills;

  let cfg = {};
  try {
    cfg = await (await fetch(API + "/config", { cache: "no-store" })).json();
  } catch (e) {
    for (const id of ["#tg-out", "#mail-out", "#push-out"]) say(id, "Serwer powiadomień nie odpowiada. Spróbuj za chwilę.", true);
    return;
  }

  // Telegram: a one-day link carries the chosen area into the bot's /start
  if (!cfg.telegram_bot) {
    $("#c-tg").setAttribute("aria-disabled", "true");
    $("#tg-go").disabled = true;
    say("#tg-out", "Bot Telegram jeszcze nie działa.");
  }
  $("#tg-go").addEventListener("click", async () => {
    const w = window.open("about:blank", "_blank");
    try {
      const { url } = await post("/telegram/link", { prefs: prefs() });
      if (w) w.location = url; else location.href = url;
      say("#tg-out", "W Telegramie naciśnij „Start”.");
    } catch (e) { if (w) w.close(); say("#tg-out", "Nie udało się: " + e.message, true); }
  });

  // e-mail: double opt-in
  if (!cfg.email) { $("#c-mail").setAttribute("aria-disabled", "true"); say("#mail-out", "E-mail jeszcze nie działa."); }
  $("#mail-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      const r = await post("/email/subscribe", { email: $("#mail").value, prefs: prefs() });
      say("#mail-out", r.confirmed ? "Zapisano nowy obszar." : "Wysłaliśmy list z linkiem. Kliknij go, aby włączyć powiadomienia (sprawdź też spam).");
    } catch (err) { say("#mail-out", "Nie udało się: " + err.message, true); }
  });

  // Web Push
  const reg = await pushState(cfg).catch((e) => { say("#push-out", e.message, true); return null; });
  navigator.serviceWorker && navigator.serviceWorker.addEventListener("message", (e) => {
    if (e.data && e.data.type === "push") {
      window.alertyLastPush = e.data;
      say("#push-out", "Ostatnie powiadomienie: " + e.data.payload.title);
    }
  });
  $("#push-go").addEventListener("click", async () => {
    try {
      if ((await Notification.requestPermission()) !== "granted") { say("#push-out", "Przeglądarka nie pozwoliła na powiadomienia.", true); return; }
      const r = reg || (await navigator.serviceWorker.register("sw.js"));
      await navigator.serviceWorker.ready;
      const sub = (await r.pushManager.getSubscription()) ||
        (await r.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: key(cfg.vapid_public_key) }));
      await post("/push/subscribe", { subscription: sub.toJSON(), prefs: prefs() });
      window.alertyPushEndpoint = sub.endpoint;
      await pushState(cfg);
    } catch (e) { say("#push-out", "Nie udało się: " + e.message, true); }
  });
  $("#push-off").addEventListener("click", async () => {
    const sub = reg && (await reg.pushManager.getSubscription());
    if (sub) { await post("/push/unsubscribe", { endpoint: sub.endpoint }).catch(() => {}); await sub.unsubscribe(); }
    say("#push-out", "Wyłączono.");
    await pushState(cfg);
  });
}

main().catch((e) => console.error(e));
