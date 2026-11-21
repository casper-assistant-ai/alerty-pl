// Alerty RCB — the changelog page: data/changelog.json, built by scripts/changelog.py from Conventional Commits.
"use strict";
const { $, h, getJSON } = RCB;
// the order of groups inside a release; the rest go under "Inne"
const ORDER = ["breaking", "feat", "fix", "perf", "revert"];
const LABEL = { breaking: "Zmiany łamiące", feat: "Nowe funkcje", fix: "Poprawki", perf: "Wydajność", revert: "Wycofane", other: "Inne zmiany" };

function bumpOf(rel, prev) {
  if (!rel.version || !prev) return "";
  const [a, b] = [rel.version, prev].map((v) => v.split(".").map(Number));
  return a[0] !== b[0] ? "major" : a[1] !== b[1] ? "minor" : "patch";
}

function release(rel, prev, repo) {
  const groups = {};
  for (const c of rel.changes) {
    const g = c.breaking ? "breaking" : ORDER.includes(c.type) ? c.type : "other";
    (groups[g] = groups[g] || []).push(c);
  }
  const kind = bumpOf(rel, prev);
  const [y, m, d] = rel.date.split("-");
  const head = h("h2", { id: rel.version ? "v" + rel.version : "niewydane" },
    rel.version ? h("span", { class: "ver mono", text: rel.version }) : h("span", { class: "ver", text: "Jeszcze niewydane" }),
    kind ? h("span", { class: "bump " + kind, text: kind }) : null,
    h("span", { class: "n mono", text: `${d}.${m}.${y}` }));
  const parts = [head];
  for (const g of [...ORDER, "other"]) {
    if (!groups[g]) continue;
    parts.push(h("h3", { text: LABEL[g] }),
      h("ul", { class: "changes" }, ...groups[g].map((c) => h("li", {},
        c.scope ? h("span", { class: "scope mono", text: c.scope }) : null,
        h("span", { text: c.text }),
        h("a", { class: "sha mono", href: `${repo}/commit/${c.sha}`, text: c.sha })))));
  }
  return h("section", { class: "month release" }, ...parts);
}

async function main() {
  RCB.strip();
  const data = await getJSON("data/changelog.json");
  const rels = data.releases;
  const versions = rels.filter((r) => r.version).map((r) => r.version);
  $("#list").replaceChildren(...rels.map((r) => release(r, versions[versions.indexOf(r.version) + 1], data.repo)));
}

main().catch((e) => { $("#list").replaceChildren(h("p", { class: "month", text: "Nie udało się wczytać historii zmian: " + e.message })); });
