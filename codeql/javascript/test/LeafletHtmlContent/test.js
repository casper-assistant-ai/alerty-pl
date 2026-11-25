// Cases for LeafletHtmlContent.ql. Lines marked BAD must be reported, OK must not.
function h(tag, props) { const e = document.createElement(tag); e.textContent = props.text; return e; }
function T(key) { return key; }

function shelters(map, p, name, n) {
  L.marker([p.lat, p.lon]).bindTooltip(p.name);                        // BAD: a field of a data object
  L.marker([p.lat, p.lon]).bindTooltip("<b>" + name + "</b>");         // BAD: concatenated from data
  L.marker([p.lat, p.lon]).bindPopup(`${p.address}, ${n} miejsc`);     // BAD: template literal with data
  const label = "Schron: " + name;
  L.marker([p.lat, p.lon]).bindTooltip(label);                         // BAD: flows from a concatenation
  map.eachLayer((l) => l.setTooltipContent(name + " (" + n + ")"));    // BAD: concatenated from data

  L.marker([p.lat, p.lon]).bindTooltip(h("span", { text: p.name }));   // OK: an element, text via textContent
  L.marker([p.lat, p.lon]).bindTooltip(() => h("span", { text: name })); // OK: a function returning an element
  L.marker([p.lat, p.lon]).bindTooltip(T("shel.me"));                 // OK: a text of the dictionaries
  L.marker([p.lat, p.lon]).bindTooltip("Jesteś tutaj");               // OK: a constant
  L.marker([p.lat, p.lon]).bindPopup("<b>" + "Schron" + "</b>");       // OK: constants only
}
