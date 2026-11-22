// Alerty RCB — service worker for Web Push. Shows each pushed alert as a system notification and opens its page on click.
"use strict";
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

self.addEventListener("push", (e) => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch (err) { d = { title: "Alert RCB", body: e.data ? e.data.text() : "" }; }
  const title = d.title || "Alert RCB";
  e.waitUntil(Promise.all([
    self.registration.showNotification(title, {
      body: d.body || "", tag: d.tag || "alert", renotify: true, icon: "icon.svg", badge: "icon.svg",
      data: { url: d.url || "./" }, requireInteraction: d.kind !== "test",
    }),
    // open pages hear about it too (the notifications page shows the last push)
    self.clients.matchAll({ includeUncontrolled: true, type: "window" })
      .then((cs) => cs.forEach((c) => c.postMessage({ type: "push", payload: d, at: new Date().toISOString() }))),
  ]));
});

self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || "./";
  e.waitUntil(self.clients.openWindow(url));
});
