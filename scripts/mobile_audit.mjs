#!/usr/bin/env node
// Mobile audit: opens every page on phone screens (360x740, 390x844, landscape 844x390) in headless
// Chrome with touch, clicks every button, tab and summary on the page one by one, and lists what a
// phone user would hit: sideways scroll, elements sticking out of the screen, tap targets under
// 24 px, text under 12 px, form fields under 16 px (iOS zooms in), targets covered by other
// elements, clipped text, fixed bars that eat the screen, exceptions. Plain Node 22+, no npm.
//
//   node scripts/mobile_audit.mjs [--base URL] [--out report.json] [--md report.md] [--shots DIR]
// Exit code 1 when anything is wrong.
import { spawn } from "node:child_process";
import { mkdtempSync, mkdirSync, writeFileSync, existsSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const args = Object.fromEntries(process.argv.slice(2).reduce((a, v, i, all) =>
  (v.startsWith("--") ? a.concat([[v.slice(2), all[i + 1]]]) : a), []));
const BASE = (args.base || "https://casper-assistant-ai.github.io/alerty-pl/").replace(/\/?$/, "/");
const PAGES = ["", "?dzien=2025-09-10", "?podklad=esri", "historia.html", "historia.html?cat=air&q=uwaga",
  "analityka.html", "analityka.html?okres=all", "powiadomienia.html", "schrony.html?lat=52.2297&lon=21.0122",
  "schrony.html", "zmiany.html", "?podklad=esri&srodek=50.5650,17.9650&zoom=15&zdjecie=2025-04-24",
  "porownaj.html?srodek=50.5650,17.9650&zoom=15&lewa=2025-03-27&prawa=2025-04-24"];
// the English and Ukrainian texts are longer or shorter than the Polish: every page again in both (docs/i18n*.js)
for (const code of ["en", "uk"]) for (const path of ["", "historia.html", "analityka.html", "powiadomienia.html",
  "schrony.html?lat=52.2297&lon=21.0122", "zmiany.html", "porownaj.html?srodek=50.5650,17.9650&zoom=15&lewa=2025-03-27&prawa=2025-04-24"]) {
  PAGES.push(path + (path.includes("?") ? "&" : "?") + "lang=" + code);
}
const VIEWPORTS = [
  { name: "360", width: 360, height: 740 },
  { name: "390", width: 390, height: 844 },
  { name: "land", width: 844, height: 390 },
];
function findChrome() {
  const c = [process.env.CHROME, "/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/usr/bin/chromium",
    "/usr/bin/chromium-browser", "/opt/google/chrome/chrome"].filter(Boolean);
  const hit = c.find((p) => existsSync(p));
  if (!hit) throw new Error("Chrome not found; set CHROME");
  return hit;
}

async function launch() {
  const dir = mkdtempSync(join(tmpdir(), "site-check-"));
  // --accept-lang: the pages without ?lang read navigator.languages; these stay Polish
  const proc = spawn(findChrome(), ["--headless=new", "--no-sandbox", "--disable-gpu", "--no-first-run", "--accept-lang=pl-PL,pl",
    "--remote-debugging-port=0", `--user-data-dir=${dir}`, "about:blank"], { stdio: ["ignore", "ignore", "pipe"] });
  const ws = await new Promise((ok, bad) => {
    let buf = "";
    const t = setTimeout(() => bad(new Error("Chrome did not start: " + buf.slice(-500))), 20000);
    proc.stderr.on("data", (d) => {
      buf += d;
      const m = buf.match(/DevTools listening on (ws:\/\/\S+)/);
      if (m) { clearTimeout(t); ok(m[1]); }
    });
  });
  return { proc, dir, ws };
}

class CDP {
  constructor(url) {
    this.id = 0; this.wait = new Map(); this.handlers = [];
    this.sock = new WebSocket(url);
    this.ready = new Promise((ok, bad) => { this.sock.onopen = ok; this.sock.onerror = bad; });
    this.sock.onmessage = (e) => {
      const m = JSON.parse(e.data);
      if (m.id && this.wait.has(m.id)) {
        const { ok, bad } = this.wait.get(m.id); this.wait.delete(m.id);
        m.error ? bad(new Error(m.error.message)) : ok(m.result);
      } else if (m.method) this.handlers.forEach((h) => h(m));
    };
  }
  send(method, params = {}, sessionId) {
    const id = ++this.id;
    this.sock.send(JSON.stringify({ id, method, params, sessionId }));
    return new Promise((ok, bad) => this.wait.set(id, { ok, bad }));
  }
  on(h) { this.handlers.push(h); }
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// The checks, run in the page. Each returns a list of problem strings.
const SCAN = `(() => {
  const p = [], W = innerWidth, H = innerHeight;
  const name = (el) => { let s = el.tagName.toLowerCase(); if (el.id) s += "#" + el.id;
    else if (el.classList.length) s += "." + [...el.classList].slice(0, 2).join(".");
    const t = (el.getAttribute("aria-label") || el.textContent || el.value || "").trim().replace(/\\s+/g, " ").slice(0, 30);
    return t ? s + ' "' + t + '"' : s; };
  const shown = (el) => { const r = el.getBoundingClientRect(); if (!r.width || !r.height) return false;
    for (let e = el; e && e.nodeType === 1; e = e.parentElement) { const cs = getComputedStyle(e);
      if (cs.display === "none" || cs.visibility === "hidden" || cs.opacity === "0") return false; }
    return !el.closest("[hidden], .visually-hidden, .leaflet-pane, .leaflet-tile-container"); };
  const clippedX = (el) => { for (let e = el.parentElement; e && e !== document.body; e = e.parentElement) {
      const o = getComputedStyle(e).overflowX; if (o !== "visible") return true; } return false; };
  if (document.documentElement.scrollWidth > W + 1) p.push("page scrolls sideways: " + document.documentElement.scrollWidth + " px on " + W);
  const all = [...document.body.querySelectorAll("*")].filter((e) => !/^(SCRIPT|STYLE|svg|path|g|rect|line|text|circle|polyline|tspan)$/i.test(e.tagName));
  const out = new Set();
  for (const el of all) { if (!shown(el) || clippedX(el)) continue; const r = el.getBoundingClientRect();
    if (r.right > W + 1 || r.left < -1) { if (![...out].some((o) => o.contains(el))) out.add(el); } }
  for (const el of out) { const r = el.getBoundingClientRect(); p.push("sticks out: " + name(el) + " spans " + Math.round(r.left) + ".." + Math.round(r.right) + " of " + W); }
  const targets = [...document.querySelectorAll("a[href], button, input:not([type=hidden]), select, textarea, summary, [role=button], [role=slider], [role=tab], label:has(input)")]
    .filter(shown).filter((el) => !el.closest(".leaflet-control-attribution") && getComputedStyle(el).pointerEvents !== "none");
  for (const el of targets) {
    let r = el.getBoundingClientRect();
    if (el.matches("input[type=radio], input[type=checkbox]") && el.closest("label")) continue;  // the label is the target
    if (el.matches("input") && getComputedStyle(el).opacity === "0") continue;
    const inline = getComputedStyle(el).display === "inline" && el.matches("a") && el.parentElement.closest("p, li, td, dd, small, .note, .rows") && (el.parentElement.textContent.trim().length > el.textContent.trim().length + 15);
    if (!inline && (r.width < 24 || r.height < 24)) p.push("tap target under 24 px: " + name(el) + " " + Math.round(r.width) + "x" + Math.round(r.height));
    const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
    if (cx > 0 && cx < W && cy > 0 && cy < H && el.getClientRects().length === 1) {  // a link wrapped over lines has no single centre
      const hit = document.elementFromPoint(cx, cy);
      // two period handles on one day sit on each other on purpose; a toast covers things for a few seconds
      if (hit && hit !== el && !el.contains(hit) && !hit.contains(el) && !(el.labels && [...el.labels].some((l) => l.contains(hit)))
          && !(el.matches("[role=slider]") && hit.matches("[role=slider]")) && !hit.closest(".toasts"))
        p.push("tap target covered: " + name(el) + " under " + name(hit)); }
  }
  for (const el of document.querySelectorAll("input:not([type=hidden]):not([type=radio]):not([type=checkbox]):not([type=range]), select, textarea"))
    if (shown(el) && parseFloat(getComputedStyle(el).fontSize) < 16) p.push("form field under 16 px (iOS zooms in on focus): " + name(el) + " " + getComputedStyle(el).fontSize);
  const small = new Map();
  const tw = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n; (n = tw.nextNode());) { if (!n.textContent.trim()) continue; const el = n.parentElement;
    if (!el || el.closest("svg, .leaflet-control-attribution") || !shown(el)) continue;
    const fs = parseFloat(getComputedStyle(el).fontSize); if (fs < 12 && !small.has(el)) small.set(el, fs); }
  for (const [el, fs] of [...small].slice(0, 12)) p.push("text under 12 px: " + name(el) + " " + fs + "px");
  if (small.size > 12) p.push("text under 12 px: " + (small.size - 12) + " more elements");
  for (const el of all) { if (!shown(el)) continue; const cs = getComputedStyle(el);
    if ((cs.overflowX === "hidden" || cs.overflow === "hidden") && cs.textOverflow !== "ellipsis" && el.scrollWidth > el.clientWidth + 2 && el.clientWidth > 0 && el.textContent.trim() && !el.closest(".leaflet-container") && !el.matches(".visually-hidden"))
      p.push("text clipped: " + name(el) + " content " + el.scrollWidth + " px in " + el.clientWidth);
    // a side-scrolling strip (tabs, chips) must not also scroll up and down under the finger
    if (/auto|scroll/.test(cs.overflowX) && /auto|scroll/.test(cs.overflowY) && el !== document.documentElement && el !== document.body && el.clientHeight > 0 && el.clientHeight < 120 && el.scrollHeight > el.clientHeight)
      p.push("strip scrolls up and down: " + name(el) + " content " + el.scrollHeight + " px in " + el.clientHeight); }
  let fixed = 0; const bars = []; for (const el of all) { const cs = getComputedStyle(el);
    if ((cs.position === "fixed" || cs.position === "sticky") && shown(el)) { const r = el.getBoundingClientRect();
      const hgt = Math.max(0, Math.min(r.bottom, H) - Math.max(r.top, 0));
      if (r.width > W * 0.6 && hgt) { fixed += hgt; bars.push(name(el) + " " + Math.round(hgt) + "px"); } } }
  if (fixed > H * 0.3) p.push("fixed or sticky bars take " + Math.round(fixed) + " px of a " + H + " px screen: " + bars.join(", "));
  const nav = document.querySelector("nav.tabs"), cur = nav && nav.querySelector('[aria-current="page"]');
  if (cur) { const a = nav.getBoundingClientRect(), b = cur.getBoundingClientRect();
    if (b.left < a.left - 1 || b.right > a.right + 1) p.push("current tab is cut off in the tab row: " + name(cur)); }
  for (const l of document.querySelectorAll("nav.tabs a")) if (shown(l) && l.getBoundingClientRect().width < 24) p.push("tab too narrow: " + name(l));
  for (const el of document.querySelectorAll('input[type="date"], select')) if (shown(el) && el.scrollWidth > el.clientWidth + 2) p.push("field value does not fit: " + name(el) + " " + el.scrollWidth + " px in " + el.clientWidth);
  return [...new Set(p)];
})()`;
// Buttons and the like to press one by one (not links: they leave the page).
const CLICKABLES = `[...document.querySelectorAll("button, summary, [role=tab], .seg label, label.chk, .legend li, .legend button")]
  .filter((el) => { const r = el.getBoundingClientRect(); return r.width && r.height && !el.disabled && !el.closest("[hidden]"); })
  .slice(0, 30).map((el, i) => { el.dataset.auditI = i; return i; })`;

async function run(cdp, sid, url, vp, problems) {
  let loaded = false;
  const h = (m) => { if (m.sessionId !== sid) return;
    if (m.method === "Page.loadEventFired") loaded = true;
    if (m.method === "Runtime.exceptionThrown") problems.push({ kind: "exception", detail: (m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text).split("\n")[0] });
    if (m.method === "Runtime.consoleAPICalled" && m.params.type === "error") problems.push({ kind: "console", detail: m.params.args.map((a) => a.value ?? a.description ?? "").join(" ").slice(0, 200) }); };
  cdp.on(h);
  await cdp.send("Page.navigate", { url }, sid);
  const t0 = Date.now(); while (!loaded && Date.now() - t0 < 30000) await sleep(100);
  await sleep(3000);
  return () => { cdp.handlers = cdp.handlers.filter((x) => x !== h); };
}
const ev = async (cdp, sid, expression) => {
  const r = await cdp.send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true }, sid);
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.text + " " + (r.exceptionDetails.exception?.description || ""));
  return r.result.value; };

async function audit(cdp, sid, path, vp) {
  const problems = [];
  await cdp.send("Emulation.setDeviceMetricsOverride", { width: vp.width, height: vp.height, deviceScaleFactor: 3, mobile: true }, sid);
  await cdp.send("Emulation.setTouchEmulationEnabled", { enabled: true, maxTouchPoints: 5 }, sid);
  const url = BASE + path;
  const off = await run(cdp, sid, url, vp, problems);
  for (const d of await ev(cdp, sid, SCAN)) problems.push({ kind: "layout", detail: d });
  if (args.shots) {
    const { data } = await cdp.send("Page.captureScreenshot", { format: "png", captureBeyondViewport: true,
      clip: { x: 0, y: 0, width: vp.width, height: Math.min(await ev(cdp, sid, "document.documentElement.scrollHeight"), 6000), scale: 1 } }, sid);
    writeFileSync(join(args.shots, `${vp.name}-${(path || "index").replace(/[^a-z0-9]+/gi, "_").replace(/^_|_$/g, "")}.png`), Buffer.from(data, "base64"));
  }
  // press each button once, then look again (the page state after the click)
  if (!path.includes("?") || path.startsWith("schrony")) {
    const n = (await ev(cdp, sid, CLICKABLES)).length;
    for (let i = 0; i < n; i++) {
      const what = await ev(cdp, sid, `(() => { const el = document.querySelector('[data-audit-i="${i}"]'); if (!el) return null;
        const t = (el.getAttribute("aria-label") || el.textContent).trim().replace(/\\s+/g, " ").slice(0, 30);
        el.scrollIntoView({ block: "center" }); el.click(); return el.tagName.toLowerCase() + ' "' + t + '"'; })()`);
      if (!what) continue;
      await sleep(600);
      // a button that leaves the page (Otwórz bota -> t.me) ends the round: the next page is not ours
      if ((await ev(cdp, sid, "location.href")) !== url) { off(); return finish(); }
      const after = await ev(cdp, sid, SCAN);
      for (const d of after) if (!problems.some((p) => p.detail === d || p.detail.endsWith(d))) problems.push({ kind: "after-click", detail: `after ${what}: ${d}` });
      if ((await ev(cdp, sid, "location.href")) !== url) { off(); return finish(); }
    }
  }
  off();
  return finish();
  function finish() { return { url, viewport: vp.name, problems }; }
}

async function main() {
  const { proc, dir, ws } = await launch();
  const results = [];
  try {
    const cdp = new CDP(ws); await cdp.ready;
    const { targetId } = await cdp.send("Target.createTarget", { url: "about:blank" });
    const { sessionId: sid } = await cdp.send("Target.attachToTarget", { targetId, flatten: true });
    for (const d of ["Page", "Runtime", "Network"]) await cdp.send(d + ".enable", {}, sid);
    // a ?lang= visit keeps its choice in localStorage ("alerty-lang"); forget it before every page's own scripts run,
    // so each page opens in the language of its URL (no ?lang: the browser's, Polish here)
    await cdp.send("Page.addScriptToEvaluateOnNewDocument", { source: 'try { localStorage.removeItem("alerty-lang"); } catch (e) {}' }, sid);
    await cdp.send("Network.setCacheDisabled", { cacheDisabled: true }, sid);
    if (args.shots) mkdirSync(args.shots, { recursive: true });
    for (const vp of VIEWPORTS) for (const path of PAGES) {
      if (vp.name === "land" && path.includes("?") && !path.startsWith("schrony")) continue;
      try { results.push(await audit(cdp, sid, path, vp)); }
      catch (e) { results.push({ url: BASE + path, viewport: vp.name, problems: [{ kind: "audit", detail: e.message.slice(0, 200) }] }); }
    }
  } finally { proc.kill("SIGKILL"); try { rmSync(dir, { recursive: true, force: true }); } catch {} }
  const bad = results.filter((r) => r.problems.length);
  if (args.out) writeFileSync(args.out, JSON.stringify({ ok: !bad.length, base: BASE, results }, null, 1));
  const md = [`Mobile audit of ${BASE}: ${bad.length ? bad.length + " of " + results.length + " page views with problems" : "all " + results.length + " page views fine"}.`, ""];
  for (const r of bad) { md.push(`### ${r.url.slice(BASE.length) || "index"} (${r.viewport})`, "");
    for (const p of r.problems) md.push(`- **${p.kind}**: ${p.detail}`); md.push(""); }
  if (args.md) writeFileSync(args.md, md.join("\n"));
  console.log(md.join("\n"));
  process.exit(bad.length ? 1 : 0);
}
main().catch((e) => { console.error(e); process.exit(2); });
