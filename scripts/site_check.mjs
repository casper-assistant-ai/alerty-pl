#!/usr/bin/env node
// Site check: opens every page of the live site in headless Chrome, the way a visitor does,
// on a desktop and a phone screen, and collects what goes wrong: JavaScript exceptions,
// console errors, failed or 4xx/5xx requests, pages that do not fill in, stale data, and broken
// markup a visitor sees (raw tags or attributes in the page text, text above the header; the HTML
// as served goes through scripts/html_check.py). --shots DIR keeps a screenshot of every page view.
// Plain Node (22+) and the Chrome DevTools Protocol; no npm.
//
//   node scripts/site_check.mjs [--base URL] [--out report.json] [--md report.md] [--shots DIR]
// CHROME=/path/to/chrome overrides the browser. Exit code 1 when anything is wrong.
import { spawn, spawnSync } from "node:child_process";
import { mkdtempSync, mkdirSync, writeFileSync, existsSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const args = Object.fromEntries(process.argv.slice(2).reduce((a, v, i, all) =>
  (v.startsWith("--") ? a.concat([[v.slice(2), all[i + 1]]]) : a), []));
const BASE = (args.base || "https://casper-assistant-ai.github.io/alerty-pl/").replace(/\/?$/, "/");
const STALE_MIN = Number(args["stale-min"] || 90);

// What each page must show once it has loaded. Each check returns a list of problems.
const COMMON = `(() => { const p = [];
  const st = document.querySelector("#strip .state");
  if (!st || /Ładowanie|Nie udało/.test(st.textContent)) p.push("status strip: " + (st ? st.textContent : "missing"));
  const ver = document.querySelector("#ver");
  if (ver && !ver.textContent.trim()) p.push("footer version is empty");
  if (document.documentElement.scrollWidth > innerWidth + 2) p.push("page scrolls sideways: " + document.documentElement.scrollWidth + "px wide on a " + innerWidth + "px screen");
  return p; })()`;
// Broken markup that shows: 22.11.2026 a link inside <meta name="description"> ended the attribute
// early and every visitor saw 'powiadomienia.">' above the header. Each line is a "markup" problem.
const MARKUP = `(() => { const p = [];
  const text = document.body.innerText;
  const tag = text.match(/<\\/?(a|abbr|b|br|button|div|em|h[1-6]|i|img|input|label|li|link|meta|nav|ol|option|p|script|section|select|small|span|strong|style|table|td|th|tr|ul)(\\s[^<>]*)?\\/?>/i);
  if (tag) p.push("raw HTML tag in the page text: " + JSON.stringify(tag[0].slice(0, 80)));
  const attr = text.match(/\\b(href|src|class|content|style|alt|name|aria-[a-z]+)\\s*=\\s*["'][^"'\\n]{0,60}["']?/);
  if (attr) p.push("raw HTML attribute in the page text: " + JSON.stringify(attr[0].slice(0, 80)));
  const tail = text.match(/[^\\s]{0,30}["']\\s*\\/?>/);
  if (tail) p.push("leftover end of a tag in the page text: " + JSON.stringify(tail[0]));
  const head = document.querySelector("header.top");
  const lead = [];
  for (const n of document.body.childNodes) {
    if (n === head) break;
    if (n.nodeType === 3 && n.textContent.trim()) lead.push(n.textContent.trim());
    else if (n.nodeType === 1 && !/^(SCRIPT|STYLE|LINK|META|NOSCRIPT|TEMPLATE)$/.test(n.tagName) && n.innerText && n.innerText.trim()) lead.push(n.innerText.trim());
  }
  if (lead.length) p.push("text above the header: " + JSON.stringify(lead.join(" ").slice(0, 80)));
  if (head && scrollY < 2 && head.getBoundingClientRect().top > 2) p.push("header starts " + Math.round(head.getBoundingClientRect().top) + "px below the top of the screen");
  const desc = document.querySelector('meta[name="description"]');
  if (!desc || !desc.content.trim()) p.push('no <meta name="description">');
  else if (/[<>]/.test(desc.content)) p.push('<meta name="description"> holds markup: ' + JSON.stringify(desc.content.slice(0, 80)));
  for (const el of document.querySelectorAll("header.top, main, footer, h1, h2, nav")) {
    const r = el.getBoundingClientRect();
    if (r.width && (r.right > innerWidth + 2 || r.left < -2)) p.push((el.id ? "#" + el.id : el.tagName.toLowerCase()) + " sticks out of the screen: " + Math.round(r.left) + ".." + Math.round(r.right) + "px of " + innerWidth);
  }
  return p; })()`;
const PAGES = [
  { path: "", name: "Mapa", check: `(() => { const p = [];
      if (document.querySelectorAll("#map path.pow, .leaflet-interactive").length < 300) p.push("map: powiaty not drawn");
      if (!document.querySelector("#active li")) p.push("list of active alerts is empty");
      if (!document.querySelector("#brush") || !document.querySelector("#spark path")) p.push("period picker is missing");
      return p; })()` },
  { path: "?dzien=2026-11-20", name: "Mapa, dzień 20.11", check: `(() => { const p = [];
      if (document.querySelectorAll("#map path.pow, .leaflet-interactive").length < 300) p.push("map: powiaty not drawn");
      if (document.querySelectorAll("#map path.hit").length < 40) p.push("map: the alerts of 20.11.2026 (air alert in 2 voivodeships) are not coloured");
      return p; })()` },
  { path: "?dzien=2025-09-10", name: "Mapa, zalot dronów 10.09.2025", check: `(() => { const p = [];
      if (document.querySelectorAll(".raid-tick").length < 5) p.push("slider: red days of missile and drone incursions are missing");
      const card = document.querySelector("#raid");
      if (!card || card.hidden || !card.querySelector(".raid-src a")) p.push("incursion card with its sources is not shown for 10.09.2025");
      if (!document.querySelector(".leaflet-raid-pane .raid-trail, .leaflet-raid-pane .raid-route")) p.push("incursion routes are not drawn on the map");
      return p; })()` },
  { path: "?dzien=2026-08-15&podklad=nasa&pozary=1", name: "Mapa, NASA i pożary 15.08", check: `(() => { const p = [];
      if (document.querySelectorAll(".leaflet-interactive").length < 300) p.push("map: powiaty not drawn");
      if (document.querySelectorAll(".leaflet-tile-pane img.leaflet-tile-loaded").length < 4) p.push("NASA true colour tiles did not load");
      if (!document.querySelector(".leaflet-fires-pane img")) p.push("NASA FIRMS fire layer is missing");
      if (!/15\.08\.2026/.test(document.querySelector("#day-label")?.textContent || "")) p.push("day slider did not open 15.08.2026");
      return p; })()` },
  { path: "?podklad=esri", name: "Mapa, Esri Wayback", check: `(() => { const p = [];
      if (document.querySelectorAll(".leaflet-tile-pane img.leaflet-tile-loaded").length < 4) p.push("Esri Wayback tiles did not load");
      if (!document.querySelector("#wayback option")) p.push("Esri Wayback date list is empty");
      return p; })()` },
  { path: "historia.html", name: "Historia", check: `(() => { const p = [];
      if (document.querySelectorAll("#list li").length < 20) p.push("history list has fewer than 20 rows");
      if (!/alert/.test(document.querySelector("#count")?.textContent || "")) p.push("history count line is empty");
      return p; })()` },
  { path: "historia.html?cat=air&q=uwaga", name: "Historia, filtr", check: `(() => [])()` },
  { path: "analityka.html", name: "Analityka", check: `(() => { const p = [];
      if (document.querySelectorAll("main svg rect, main svg path").length < 20) p.push("analytics charts are empty");
      if (!/\\d/.test(document.querySelector(".stats")?.textContent || "")) p.push("analytics stats have no numbers");
      return p; })()` },
  { path: "analityka.html?okres=all", name: "Analityka, od 2021", check: `(() => [])()` },
  { path: "schrony.html?lat=52.2297&lon=21.0122", name: "Schrony, Warszawa", check: `(() => { const p = [];
      if (document.querySelectorAll("#near li .btn.primary").length < 5) p.push("shelters: fewer than 5 nearest points with a Nawiguj button");
      if (!/\\d+(,\\d)? (m|km)/.test(document.querySelector("#near .sh-d")?.textContent || "")) p.push("shelters: no distance in the list");
      if (!/punktów/.test(document.querySelector("#about-data")?.textContent || "")) p.push("shelters: data note is empty");
      return p; })()` },
  { path: "zmiany.html", name: "Zmiany", check: `(() => { const p = [];
      if (!document.querySelector("#list .release")) p.push("changelog shows no releases");
      return p; })()` },
];
const VIEWPORTS = [
  { name: "desktop", width: 1440, height: 900, mobile: false, scale: 1 },
  { name: "phone", width: 390, height: 844, mobile: true, scale: 2 },
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
  const proc = spawn(findChrome(), ["--headless=new", "--no-sandbox", "--disable-gpu", "--no-first-run",
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

async function visit(cdp, sid, page, vp) {
  const problems = [];
  const origin = new URL(BASE).origin;
  const pending = new Map();
  let loaded = false;
  const handler = (m) => {
    if (m.sessionId !== sid) return;
    const p = m.params;
    switch (m.method) {
      case "Runtime.exceptionThrown":
        problems.push({ kind: "exception", detail: (p.exceptionDetails.exception?.description || p.exceptionDetails.text).split("\n").slice(0, 3).join(" | ") });
        break;
      case "Runtime.consoleAPICalled":
        if (p.type === "error" || p.type === "assert")
          problems.push({ kind: "console", detail: p.args.map((a) => a.value ?? a.description ?? "").join(" ").slice(0, 300) });
        break;
      case "Network.requestWillBeSent": pending.set(p.requestId, p.request.url); break;
      case "Network.responseReceived":
        if (p.response.status >= 400) {
          const own = p.response.url.startsWith(origin);
          problems.push({ kind: own ? "http" : "http-3rd", detail: `${p.response.status} ${p.response.url.slice(0, 200)}` });
        }
        break;
      case "Network.loadingFailed": {
        const url = pending.get(p.requestId) || "?";
        if (!/ERR_ABORTED|ERR_BLOCKED_BY_CLIENT/.test(p.errorText) && !p.canceled)
          problems.push({ kind: url.startsWith(origin) ? "network" : "network-3rd", detail: `${p.errorText} ${url.slice(0, 200)}` });
        break;
      }
      case "Page.loadEventFired": loaded = true; break;
    }
  };
  cdp.on(handler);
  await cdp.send("Emulation.setDeviceMetricsOverride", { width: vp.width, height: vp.height, deviceScaleFactor: vp.scale, mobile: vp.mobile }, sid);
  const url = BASE + page.path;
  const t0 = Date.now();
  await cdp.send("Page.navigate", { url }, sid);
  while (!loaded && Date.now() - t0 < 30000) await sleep(100);
  if (!loaded) problems.push({ kind: "timeout", detail: "page did not load in 30 s" });
  await sleep(3500); // data files and charts load after the load event
  for (const [kind, expr] of [["content", COMMON], ["markup", MARKUP], ["content", page.check]]) {
    const r = await cdp.send("Runtime.evaluate", { expression: expr, returnByValue: true }, sid);
    if (r.exceptionDetails) problems.push({ kind: "check", detail: "check failed: " + r.exceptionDetails.text });
    else for (const d of r.result.value || []) problems.push({ kind, detail: d });
  }
  let shot;
  if (args.shots) {
    await cdp.send("Runtime.evaluate", { expression: "scrollTo(0, 0)" }, sid);
    const { data } = await cdp.send("Page.captureScreenshot", { format: "png" }, sid);
    shot = join(args.shots, `${vp.name}-${(page.path || "index").replace(/[^a-z0-9]+/gi, "_").replace(/^_|_$/g, "")}.png`);
    writeFileSync(shot, Buffer.from(data, "base64"));
  }
  cdp.handlers = cdp.handlers.filter((h) => h !== handler);
  // a few failed 3rd-party tiles (a satellite day with no image) are normal; many are not
  const third = problems.filter((p) => p.kind.endsWith("-3rd"));
  const rest = problems.filter((p) => !p.kind.endsWith("-3rd"));
  if (third.length > 8) rest.push({ kind: "3rd-party", detail: `${third.length} failed requests to other sites, e.g. ${third[0].detail}` });
  return { page: page.name, url, viewport: vp.name, ms: Date.now() - t0, problems: rest, ...(shot ? { shot } : {}) };
}

// The HTML of each page as the server sends it, through scripts/html_check.py (plain Python).
async function served() {
  const out = [];
  const files = [...new Set(PAGES.map((p) => new URL(BASE + p.path).pathname))];
  const tmp = mkdtempSync(join(tmpdir(), "site-html-"));
  const checker = join(dirname(fileURLToPath(import.meta.url)), "html_check.py");
  try {
    for (const path of files) {
      const url = new URL(path, BASE).href;
      try {
        const r = await fetch(url + "?t=" + Date.now());
        if (!r.ok) continue; // the page visit reports the HTTP error
        const f = join(tmp, (path.split("/").pop() || "index.html"));
        writeFileSync(f, await r.text());
        const c = spawnSync("python3", ["-I", checker, f], { encoding: "utf8" });
        const problems = c.stdout.split("\n").filter((l) => l.startsWith(f + ":"))
          .map((l) => ({ kind: "markup", detail: "HTML as served, line " + l.slice(f.length + 1).replace(/^(\d+): /, "$1: ") }));
        if (c.status !== 0 && !problems.length) problems.push({ kind: "check", detail: "html_check.py failed: " + (c.stderr || c.stdout).slice(0, 200) });
        if (problems.length) out.push({ page: "HTML " + (path.split("/").pop() || "index.html"), url, viewport: "-", problems });
      } catch (e) {
        out.push({ page: "HTML " + path, url, viewport: "-", problems: [{ kind: "http", detail: e.message }] });
      }
    }
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
  return out;
}

async function freshness() {
  try {
    const r = await fetch(BASE + "data/meta.json?t=" + Date.now());
    const m = await r.json();
    const age = (Date.now() - new Date(m.checked_at)) / 60000;
    return age > STALE_MIN ? [{ page: "data", url: BASE + "data/meta.json", viewport: "-", problems: [{ kind: "stale", detail: `data last checked ${Math.round(age)} min ago (${m.checked_at})` }] }] : [];
  } catch (e) {
    return [{ page: "data", url: BASE + "data/meta.json", viewport: "-", problems: [{ kind: "http", detail: "meta.json: " + e.message }] }];
  }
}

async function main() {
  const { proc, dir, ws } = await launch();
  const results = [];
  try {
    const cdp = new CDP(ws);
    await cdp.ready;
    const { targetId } = await cdp.send("Target.createTarget", { url: "about:blank" });
    const { sessionId: sid } = await cdp.send("Target.attachToTarget", { targetId, flatten: true });
    for (const d of ["Page", "Runtime", "Network"]) await cdp.send(d + ".enable", {}, sid);
    await cdp.send("Network.setCacheDisabled", { cacheDisabled: true }, sid);
    if (args.shots) mkdirSync(args.shots, { recursive: true });
    for (const vp of VIEWPORTS) for (const page of PAGES) results.push(await visit(cdp, sid, page, vp));
    results.push(...await served());
    results.push(...await freshness());
  } finally {
    proc.kill("SIGKILL");
    try { rmSync(dir, { recursive: true, force: true }); } catch {}
  }
  const bad = results.filter((r) => r.problems.length);
  const report = { ok: !bad.length, base: BASE, checked_at: new Date().toISOString(), pages: results.length, results };
  if (args.out) writeFileSync(args.out, JSON.stringify(report, null, 1));
  const md = [`Site check of ${BASE} at ${report.checked_at}: ${bad.length ? bad.length + " page views with problems" : "all " + results.length + " page views fine"}.`, ""];
  for (const r of bad) {
    md.push(`### ${r.page} (${r.viewport})`, r.url, "");
    for (const p of r.problems) md.push(`- **${p.kind}**: ${p.detail.replace(/\n/g, " ")}`);
    md.push("");
  }
  if (args.md) writeFileSync(args.md, md.join("\n"));
  console.log(md.join("\n"));
  process.exit(bad.length ? 1 : 0);
}

main().catch((e) => { console.error(e); process.exit(2); });
