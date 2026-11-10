// Centre de veille One Look : globe, analyse d'une tuile, seuil « inconnu » en direct, passage satellite.
"use strict";

const CLASSES = ["normal", "alerte_inondation", "alerte_incendie"];
const LABELS = { normal: "Normal", alerte_inondation: "Alerte · Inondation", alerte_incendie: "Alerte · Incendie", inconnu: "Inconnu" };
const SHORT = { normal: "normal", alerte_inondation: "inondation", alerte_incendie: "incendie", inconnu: "inconnu" };
const ICON = { normal: "●", alerte_inondation: "▲", alerte_incendie: "▲", inconnu: "?" };
const COLOR = { normal: "#6cc79b", alerte_inondation: "#f2994a", alerte_incendie: "#f2994a", inconnu: "#b9a3d6" };
const BANDS = ["B02 · bleu", "B03 · vert", "B04 · rouge", "B08 · proche IR", "B11 · IR court 1", "B12 · IR court 2"];
const $ = (id) => document.getElementById(id);
const num = (x, d = 2) => x.toFixed(d).replace(".", ",");
const pct = (x) => `${Math.round(100 * x)} %`;

const state = { meta: null, catalog: [], byId: {}, seuil: 0.67, current: null, analysis: null, view: "naturel",
  toggles: { verite: false, regard: false }, passes: 0, playing: false, playIndex: 0, timer: null, globe: null, feed: [] };

const kind = (d) => (d === "normal" ? "normal" : d === "inconnu" ? "unknown" : "alert");
function decide(probs, seuil = state.seuil) {
  let k = 0;
  probs.forEach((p, i) => { if (p > probs[k]) k = i; });
  return probs[k] < seuil ? "inconnu" : CLASSES[k];
}

// ---------- Démarrage ----------
async function start() {
  const [meta, catalog] = await Promise.all([fetch("api/meta").then((r) => r.json()), fetch("api/catalog").then((r) => r.json())]);
  state.meta = meta;
  state.catalog = catalog;
  catalog.forEach((t) => (state.byId[t.id] = t));
  state.seuil = meta.seuil;
  $("seuil").value = meta.seuil;
  $("chip-model").innerHTML = `Modèle <b>${meta.modele.replace("mobilenet v3 small", "MobileNetV3-Small")}</b> · <b>${num(meta.taille_mo, 1)} Mo</b>`;
  const sel = $("goto");
  const groups = { "Passage satellite": meta.passage.map((p) => p.id), "Lot inconnu": catalog.filter((t) => t.partie === "inconnu").map((t) => t.id) };
  for (const [name, ids] of Object.entries(groups)) {
    const og = document.createElement("optgroup");
    og.label = name;
    ids.forEach((id) => { const o = document.createElement("option"); o.value = id; o.textContent = `${id} · ${state.byId[id]?.lieu ?? ""}`; og.append(o); });
    sel.append(og);
  }
  buildCube();
  layout();
  new ResizeObserver(layout).observe(document.querySelector("main"));
  initGlobe();
  refreshThreshold();
  tick();
  setInterval(tick, 1000);
}

function layout() {
  // La tuile reste carrée : son côté suit la hauteur disponible dans le panneau central
  const panel = document.querySelector(".tile-panel");
  const used = [...panel.children].filter((el) => el.id !== "tile").reduce((h, el) => h + el.offsetHeight + 10, 0);
  const side = Math.max(260, Math.floor(panel.clientHeight - 28 - used));
  $("tile").style.width = $("tile").style.height = `${side}px`;
  panel.style.width = `${side + 34}px`;
}

function tick() {
  const d = new Date();
  $("clock").textContent = `${d.toLocaleDateString("fr-FR")} ${d.toLocaleTimeString("fr-FR")} UTC${-d.getTimezoneOffset() / 60 >= 0 ? "+" : ""}${-d.getTimezoneOffset() / 60}`;
}

// ---------- Globe : 3D (globe.gl) si WebGL, sinon 2D (d3) ----------
function webgl() {
  try { const c = document.createElement("canvas"); return !!(c.getContext("webgl2") || c.getContext("webgl")); } catch { return false; }
}

function orbit() {
  const pts = [];
  for (let l = -180; l <= 180; l += 3) pts.push([l, 58 * Math.sin(((l + 40) * Math.PI) / 180)]);
  return pts;
}

function initGlobe() {
  const el = $("globe");
  const points = () => state.catalog.filter((t) => t.lat != null);
  if (webgl() && window.Globe) {
    const g = Globe()(el)
      .backgroundColor("rgba(0,0,0,0)")
      .globeImageUrl("vendor/earth-night.jpg").bumpImageUrl("vendor/earth-topology.png")
      .atmosphereColor("#6fb1e3").atmosphereAltitude(0.2)
      .pointLat((t) => t.lat).pointLng((t) => t.lon)
      .pointColor((t) => COLOR[decide(t.probs)])
      .pointAltitude((t) => (decide(t.probs) === "normal" ? 0.01 : decide(t.probs) === "inconnu" ? 0.07 : 0.16))
      .pointRadius((t) => (decide(t.probs) === "normal" ? 0.22 : 0.42))
      .pointLabel((t) => `<div class="globe-tip"><b>${t.id}</b><br>${t.lieu ?? ""}<br>${LABELS[decide(t.probs)]}</div>`)
      .onPointClick((t) => { stopPlay(); select(t.id); })
      .ringColor(() => (r) => `rgba(111,177,227,${1 - r})`).ringMaxRadius(7).ringPropagationSpeed(3).ringRepeatPeriod(900)
      .pathsData([orbit()]).pathPoints((d) => d).pathPointLat((p) => p[1]).pathPointLng((p) => p[0]).pathPointAlt(0.13)
      .pathColor(() => ["rgba(111,177,227,0.05)", "rgba(111,177,227,1)"]).pathStroke(1.3)
      .pathDashLength(0.12).pathDashGap(0.03).pathDashAnimateTime(5000)
      .pointsData(points());
    g.pointOfView({ lat: 15, lng: -40, altitude: 2.3 });
    g.controls().autoRotate = true;
    g.controls().autoRotateSpeed = 0.45;
    const fit = () => g.width(el.clientWidth).height(el.clientHeight);
    new ResizeObserver(fit).observe(el);
    fit();
    state.globe = {
      refresh: () => g.pointsData(points()),
      focus: (t) => {
        if (t.lat == null) return;
        g.controls().autoRotate = false;
        g.pointOfView({ lat: t.lat, lng: t.lon, altitude: 1.5 }, 1600);
        g.ringsData([{ lat: t.lat, lng: t.lon }]);
        clearTimeout(state.spin);
        state.spin = setTimeout(() => (g.controls().autoRotate = true), 9000);
      },
    };
  } else {
    state.globe = flatGlobe(el, points);
  }
}

function flatGlobe(el, points) {
  // Repli sans WebGL : globe orthographique en SVG, rotation automatique et à la souris
  const svg = d3.select(el).append("svg");
  const proj = d3.geoOrthographic().rotate([40, -15]).clipAngle(90);
  const path = d3.geoPath(proj);
  const sphere = svg.append("path").datum({ type: "Sphere" }).attr("fill", "#0f1d29").attr("stroke", "#2c3b47");
  const grat = svg.append("path").datum(d3.geoGraticule10()).attr("fill", "none").attr("stroke", "#1e2b36");
  const land = svg.append("path").attr("fill", "#2a4052").attr("stroke", "#3a5468").attr("stroke-width", 0.5);
  const track = svg.append("path").datum({ type: "LineString", coordinates: orbit() }).attr("fill", "none").attr("stroke", "#6fb1e3").attr("stroke-dasharray", "4 4");
  const dots = svg.append("g");
  const ring = svg.append("circle").attr("r", 0).attr("fill", "none").attr("stroke", "#6fb1e3").attr("stroke-width", 2);
  let focusOn = null, auto = true;
  fetch("vendor/countries-110m.json").then((r) => r.json()).then((w) => { land.datum(topojson.feature(w, w.objects.land)); draw(); });
  function size() {
    const w = el.clientWidth, h = el.clientHeight;
    svg.attr("viewBox", `0 0 ${w} ${h}`);
    proj.translate([w / 2, h / 2]).scale(Math.min(w, h) / 2 - 8);
  }
  function draw() {
    sphere.attr("d", path); grat.attr("d", path); land.attr("d", path); track.attr("d", path);
    const center = proj.invert([el.clientWidth / 2, el.clientHeight / 2]);
    dots.selectAll("circle").data(points(), (t) => t.id).join("circle")
      .attr("r", (t) => (decide(t.probs) === "normal" ? 2.2 : 3.8)).attr("fill", (t) => COLOR[decide(t.probs)])
      .attr("opacity", (t) => (decide(t.probs) === "normal" ? 0.6 : 1)).style("cursor", "pointer")
      .attr("display", (t) => (d3.geoDistance([t.lon, t.lat], center) > Math.PI / 2 ? "none" : null))
      .attr("cx", (t) => proj([t.lon, t.lat])[0]).attr("cy", (t) => proj([t.lon, t.lat])[1])
      .on("click", (e, t) => { stopPlay(); select(t.id); });
    if (focusOn) { const [x, y] = proj([focusOn.lon, focusOn.lat]); ring.attr("cx", x).attr("cy", y); }
  }
  svg.call(d3.drag().on("drag", (e) => { auto = false; const r = proj.rotate(); proj.rotate([r[0] + e.dx / 3, r[1] - e.dy / 3]); draw(); }).on("end", () => setTimeout(() => (auto = true), 6000)));
  d3.timer((t) => { if (auto) { const r = proj.rotate(); proj.rotate([r[0] + 0.08, r[1]]); draw(); } ring.attr("r", 6 + (t / 60) % 14).attr("opacity", 1 - ((t / 60) % 14) / 14); });
  new ResizeObserver(() => { size(); draw(); }).observe(el);
  size();
  return {
    refresh: draw,
    focus: (t) => {
      if (t.lat == null) return;
      focusOn = t; auto = false;
      d3.transition().duration(1400).tween("rotate", () => {
        const r = d3.interpolate(proj.rotate(), [-t.lon, -t.lat]);
        return (k) => { proj.rotate(r(k)); draw(); };
      });
      clearTimeout(state.spin);
      state.spin = setTimeout(() => (auto = true), 9000);
    },
  };
}

// ---------- Seuil « inconnu » et indicateurs ----------
function refreshThreshold() {
  const s = state.seuil;
  $("seuil-val").textContent = num(s);
  $("chip-seuil").innerHTML = `Seuil « inconnu » <b>${num(s)}</b>`;
  const test = state.catalog.filter((t) => t.partie === "test" && CLASSES.includes(t.verite));
  const rate = (rows, ok) => (rows.length ? rows.filter(ok).length / rows.length : 0);
  const floods = test.filter((t) => t.verite === "alerte_inondation");
  const fires = test.filter((t) => t.verite === "alerte_incendie");
  const normals = test.filter((t) => t.verite === "normal");
  const traps = normals.filter((t) => t.piege_eau);
  const alerted = (t) => decide(t.probs).startsWith("alerte");
  const unknown = state.catalog.filter((t) => t.partie === "inconnu" && t.visible === "oui");
  const kpis = [
    [pct(rate(floods, (t) => decide(t.probs) === "alerte_inondation")), `inondations détectées<br>(${floods.length} au test)`],
    [pct(rate(fires, (t) => decide(t.probs) === "alerte_incendie")), `incendies détectés<br>(${fires.length} au test)`],
    [`${num(100 * rate(normals, alerted), 1)} %`, `fausses alertes<br>(${normals.length} normales)`],
    [`${traps.filter(alerted).length} / ${traps.length}`, "pièges d'eau en alerte<br>seuils classiques : 42 / 48"],
    [`${unknown.filter((t) => decide(t.probs) === "inconnu").length} / ${unknown.length}`, "phénomènes jamais vus<br>reconnus « inconnu »"],
    [`${state.catalog.filter((t) => decide(t.probs) === "inconnu").length}`, `tuiles en « inconnu »<br>sur ${state.catalog.length}`],
  ];
  $("kpis").innerHTML = kpis.map(([v, l]) => `<div class="kpi"><div class="v">${v}</div><div class="l">${l}</div></div>`).join("");
  const alerts = state.catalog.filter(alerted).length;
  $("globe-title").textContent = `${state.catalog.length} tuiles jamais vues · test et lot « inconnu »`;
  $("globe-count").textContent = `${alerts} alertes`;
  state.globe?.refresh();
  if (state.analysis) showDecision(state.analysis, false);
}

// ---------- Une tuile ----------
async function select(id) {
  const t = state.byId[id];
  if (!t) return;
  state.current = id;
  $("empty").style.display = "none";
  $("tile-title").textContent = `${id} · ${t.lieu ?? ""}`;
  $("tile-coords").textContent = t.lat != null ? coords(t.lat, t.lon) : "";
  $("hud").textContent = `512 × 512 px · 10 m · 5,12 km · 6 bandes${t.date ? " · " + t.date : ""}`;
  state.globe.focus(t);
  setImages(id);
  $("tile").classList.add("scanning");
  $("badge").className = "badge disp idle";
  $("badge").textContent = "Analyse…";
  $("bars").innerHTML = "";
  $("truth").textContent = "";
  $("occ").classList.remove("show");
  $("robust").classList.remove("show");
  const started = performance.now();
  try {
    const a = await fetch(`api/analyse/${encodeURIComponent(id)}`).then((r) => { if (!r.ok) throw new Error(r.statusText); return r.json(); });
    await new Promise((r) => setTimeout(r, Math.max(0, 900 - (performance.now() - started))));
    if (state.current !== id) return;
    state.analysis = a;
    state.passes += 1;
    $("tile").classList.remove("scanning");
    drawOcclusion(a.occlusion);
    showDecision(a, true);
    showDescription(a);
    log(a);
  } catch (err) {
    $("tile").classList.remove("scanning");
    toast(`Analyse impossible : ${err.message}`);
  }
}

function coords(lat, lon) {
  return `${num(Math.abs(lat), 1)}° ${lat >= 0 ? "N" : "S"} · ${num(Math.abs(lon), 1)}° ${lon >= 0 ? "E" : "O"}`;
}

function setImages(id) {
  const base = `api/tile/${encodeURIComponent(id)}`;
  $("img-base").src = `${base}/${state.view}`;
  $("img-truth").src = `${base}/verite`;
  $("img-truth").classList.toggle("show", state.toggles.verite);
  document.querySelectorAll("#stack img").forEach((img, k) => (img.src = `${base}/b${k}`));
}

function drawOcclusion(grid) {
  const c = $("occ"), ctx = c.getContext("2d");
  const n = grid.length, max = Math.max(3, ...grid.flat());
  c.width = c.height = n;
  grid.forEach((row, i) => row.forEach((v, j) => {
    const a = Math.max(0, v) / max;
    ctx.fillStyle = `rgba(242,153,74,${0.85 * a})`;
    ctx.clearRect(j, i, 1, 1);
    ctx.fillRect(j, i, 1, 1);
  }));
  c.classList.toggle("show", state.toggles.regard);
  state.robust = Math.max(...grid.flat()) < 3;
  $("robust").classList.toggle("show", state.toggles.regard && state.robust);
}

function showDecision(a, animate) {
  const t = a.tuile;
  const probs = CLASSES.map((c) => a.probs[c]);
  const d = decide(probs);
  const badge = $("badge");
  badge.className = `badge disp ${kind(d)}${animate ? " pop" : ""}`;
  badge.textContent = `${ICON[d]} ${LABELS[d]}`;
  $("pass").textContent = `passe n° ${state.passes} · ${num(a.temps_ms, 1)} ms`;
  $("chip-time").innerHTML = `Une passe <b>${num(a.temps_ms, 1)} ms</b> · 1 cœur de processeur`;
  $("bars").innerHTML = CLASSES.map((c, i) => `<div class="bar"><span>${SHORT[c][0].toUpperCase() + SHORT[c].slice(1)}</span><div class="t"><div style="background:${COLOR[c]}" data-w="${100 * probs[i]}"></div></div><span class="mono">${num(probs[i])}</span></div>`).join("");
  requestAnimationFrame(() => document.querySelectorAll("#bars .t div").forEach((el) => (el.style.width = `${el.dataset.w}%`)));
  $("truth").innerHTML = truthLine(t, d);
  const title = document.querySelector("#desc .t");
  if (title) title.textContent = headline(d, probs);
}

function truthLine(t, d) {
  if (t.partie === "depot") return "Image déposée : pas de vérité terrain connue.";
  if (t.partie === "inconnu") {
    const ok = d === "inconnu";
    return `Jamais vu : <b>${t.note}</b>.<br>Réponse attendue : inconnu · <span class="${ok ? "ok" : "ko"}">${ok ? "reconnu ✓" : `répond ${SHORT[d]} ✗`}</span>`;
  }
  if (t.verite === "ambigu") return "Vérité terrain : <b>ambiguë</b> (anomalie entre 0,5 et 5 %, ou ancien feu récent) · pas de bonne réponse unique.";
  const share = t.verite === "alerte_inondation" ? ` sur <b>${pct(t.inondation)}</b> de la tuile` : t.verite === "alerte_incendie" ? ` sur <b>${pct(t.brule)}</b> de la tuile` : "";
  const ok = d === t.verite;
  return `Vérité terrain : <b>${SHORT[t.verite]}</b>${share} · <span class="${ok ? "ok" : "ko"}">${ok ? "décision juste ✓" : "décision fausse ✗"}</span>`;
}

function headline(d, probs) {
  let k = 0;
  probs.forEach((p, i) => { if (p > probs[k]) k = i; });
  const p = probs[k];
  if (d === "inconnu") return `Inconnu : confiance ${num(p)}, sous le seuil ${num(state.seuil)}. Le modèle pencherait pour « ${SHORT[CLASSES[k]]} ».`;
  const words = p >= 0.9 ? "très sûr de lui" : p >= 0.75 ? "assez sûr" : "hésitant";
  return `${LABELS[d]}, le modèle est ${words} (confiance ${num(p)}).`;
}

function showDescription(a) {
  const d = a.description;
  const probs = CLASSES.map((c) => a.probs[c]);
  $("desc").innerHTML = `<p class="t">${headline(decide(probs), probs)}</p>${d.contexte ? `<p class="c">${d.contexte}</p>` : ""}<ul>${d.constats.map((c, i) => `<li class="new" style="animation-delay:${0.12 * i}s">${c}</li>`).join("")}</ul>`;
  $("desc-time").textContent = `mesures et occlusion : ${num(a.occlusion_ms / 1000, 1)} s`;
}

function log(a) {
  const d = decide(CLASSES.map((c) => a.probs[c]));
  const t = a.tuile;
  const expected = t.partie === "inconnu" ? "inconnu" : t.verite;
  const mark = !expected || expected === "ambigu" ? "" : expected === d ? '<span class="ok">✓</span>' : '<span class="ko">✗</span>';
  state.feed.unshift({ id: a.id, d, mark });
  state.feed = state.feed.slice(0, 30);
  $("feed").innerHTML = state.feed.map((f) => `<li data-id="${f.id}"><span class="tag ${kind(f.d)}">${LABELS[f.d]}</span><span class="id">${f.id}</span>${f.mark}</li>`).join("");
  $("feed-count").textContent = `${state.passes} passe${state.passes > 1 ? "s" : ""}`;
}

// ---------- Cube des 6 bandes ----------
function buildCube() {
  $("stack").innerHTML = BANDS.map((b, k) => `<div class="layer" style="--k:${k};transform:translateZ(${k * 22}px)"><img alt="${b}"><span class="lab">${b}</span></div>`).join("");
}

// ---------- Passage satellite ----------
function play() {
  if (state.playing) return stopPlay();
  state.playing = true;
  $("play").textContent = "❚❚ Pause";
  step();
}
async function step() {
  if (!state.playing) return;
  const list = state.meta.passage;
  const p = list[state.playIndex % list.length];
  state.playIndex += 1;
  $("recit").textContent = p.recit;
  $("recit").classList.add("show");
  if (!state.toggles.regard) toggle("regard", true);
  await select(p.id);
  if (state.playing) state.timer = setTimeout(step, 9000);
}
function stopPlay() {
  state.playing = false;
  clearTimeout(state.timer);
  $("play").textContent = "▶ Passage satellite";
}

// ---------- Commandes ----------
function toggle(name, value) {
  state.toggles[name] = value ?? !state.toggles[name];
  document.querySelector(`[data-toggle="${name}"]`).classList.toggle("on", state.toggles[name]);
  (name === "verite" ? $("img-truth") : $("occ")).classList.toggle("show", state.toggles[name]);
  if (name === "regard") $("robust").classList.toggle("show", state.toggles.regard && !!state.robust && !!state.analysis);
}

document.querySelectorAll("[data-view]").forEach((b) => b.addEventListener("click", () => {
  state.view = b.dataset.view;
  document.querySelectorAll("[data-view]").forEach((x) => x.classList.toggle("on", x === b));
  if (state.current) $("img-base").src = `api/tile/${encodeURIComponent(state.current)}/${state.view}`;
}));
document.querySelectorAll("[data-toggle]").forEach((b) => b.addEventListener("click", () => toggle(b.dataset.toggle)));
$("seuil").addEventListener("input", (e) => { state.seuil = parseFloat(e.target.value); refreshThreshold(); });
$("play").addEventListener("click", play);
$("goto").addEventListener("change", (e) => { if (e.target.value) { stopPlay(); $("recit").classList.remove("show"); select(e.target.value); } e.target.value = ""; });
$("feed").addEventListener("click", (e) => { const li = e.target.closest("li"); if (li) { stopPlay(); select(li.dataset.id); } });
document.addEventListener("keydown", (e) => { if (e.code === "Space" && e.target.tagName !== "SELECT") { e.preventDefault(); play(); } });

// ---------- Dépôt d'un GeoTIFF ----------
async function upload(file) {
  stopPlay();
  const form = new FormData();
  form.append("file", file);
  try {
    const r = await fetch("api/depot", { method: "POST", body: form });
    const body = await r.json();
    if (!r.ok) throw new Error(body.detail || r.statusText);
    body.probs = [1, 0, 0];
    state.byId[body.id] = body;
    $("recit").textContent = `Image déposée : ${file.name}`;
    $("recit").classList.add("show");
    await select(body.id);
    if (state.analysis?.id === body.id) {
      body.probs = CLASSES.map((c) => state.analysis.probs[c]);
      if (body.lat != null) { state.catalog.push(body); refreshThreshold(); }
    }
  } catch (err) {
    toast(`Dépôt refusé : ${err.message}`);
  }
}
$("file").addEventListener("change", (e) => e.target.files[0] && upload(e.target.files[0]));
let depth = 0;
window.addEventListener("dragenter", (e) => { e.preventDefault(); depth += 1; $("drop").classList.add("show"); });
window.addEventListener("dragleave", () => { depth -= 1; if (depth <= 0) $("drop").classList.remove("show"); });
window.addEventListener("dragover", (e) => e.preventDefault());
window.addEventListener("drop", (e) => { e.preventDefault(); depth = 0; $("drop").classList.remove("show"); const f = e.dataTransfer.files[0]; if (f) upload(f); });

function toast(text) {
  $("toast").textContent = text;
  $("toast").classList.add("show");
  setTimeout(() => $("toast").classList.remove("show"), 5000);
}

start();
