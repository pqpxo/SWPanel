"use strict";

const GRID = 4, MIN_SIZE = 20;
const clamp = (v, low, high) => Math.max(low, Math.min(high, v));
const ALIGNS = { TOP_LEFT: [0, 0], TOP_MID: [.5, 0], TOP_RIGHT: [1, 0], LEFT_MID: [0, .5], CENTER: [.5, .5],
  RIGHT_MID: [1, .5], BOTTOM_LEFT: [0, 1], BOTTOM_MID: [.5, 1], BOTTOM_RIGHT: [1, 1] };
const TEXT_SIZES = Array.from({ length: 20 }, (_, i) => 10 + i * 2);
const ICON_SIZES = [16, 20, 24, 32, 40, 48, 64, 72, 96];
/* Font value: [name shown, family in the preview, weight]. Montserrat is built into the panel. */
const FONTS = {
  montserrat: ["Montserrat", "system-ui, sans-serif", 400],
  roboto: ["Roboto", "Roboto", 400], roboto_bold: ["Roboto Bold", "Roboto", 700],
  inter: ["Inter", "Inter", 400], inter_bold: ["Inter Bold", "Inter", 700],
  poppins: ["Poppins", "Poppins", 400], poppins_bold: ["Poppins Bold", "Poppins", 700],
  oswald: ["Oswald", "Oswald", 400], oswald_bold: ["Oswald Bold", "Oswald", 700],
};
const SHADOW = { shadow_width: 0, shadow_color: "#000000", shadow_opa: 50, shadow_offset_x: 0, shadow_offset_y: 4, shadow_spread: 0 };
const SHADOW_KEYS = Object.keys(SHADOW);
const SIZED = new Set(["toggle", "sensor", "status", "page_button", "slider", "image"]);
/* Theme setting: the element settings it changes across the whole design. */
const THEME_TARGETS = { tile_bg: ["bg"], border: ["border"], tile_on: ["bg_on", "bar_color"], text: ["text_color", "value_color"],
  icon: ["icon_color", "knob_color"], font: ["font"], radius: ["radius"] };
const THEME_COLOURS = [["page_bg", "Page background", "#1E222B"], ["tile_bg", "Tile background", "#2F3542"], ["border", "Border", "#3B4252"],
  ["tile_on", "Tile when on", "#4A5572"], ["text", "Text", "#E4E8F0"], ["icon", "Icons", "#D8DCE4"]];
const ICON_PAGE = 240;
const LIVE_MS = 3000;
/* The states the panel treats as off (see panel.yaml.j2). */
const NOT_ON = ["off", "unavailable", "unknown", "standby"];
const TILE = { radius: 12, bg: "#2F3542", border: "#3B4252", text_size: 16, text_color: "#E4E8F0", icon_size: 32, font: "montserrat", ...SHADOW };

const TYPES = {
  toggle: { label: "Toggle tile", defaults: { ...TILE, w: 219, h: 102, text: "New tile", icon: "lightbulb-outline",
    entity: "light.example", show_state: true, bg_on: "#4A5572", icon_color: "#D8DCE4", icon_color_on: "#F2CF66", off_opacity: 100 } },
  sensor: { label: "Sensor tile", defaults: { ...TILE, w: 219, h: 116, text: "New sensor", icon: "gauge", icon_color: "#F2B84B",
    entity: "sensor.example", unit: "", decimals: 1, value_size: 22, value_color: "#FFFFFF" } },
  status: { label: "Status tile", defaults: { ...TILE, w: 219, h: 116, text: "New status", entity: "binary_sensor.example", off_opacity: 100,
    on_state: "on", on_text: "On", on_icon: "check-circle-outline", on_color: "#6BCB77",
    off_state: "off", off_text: "Off", off_icon: "circle-outline", off_color: "#F2B84B" } },
  page_button: { label: "Page button", defaults: { radius: 17, bg: "#2F3542", border: "#3B4252", w: 144, h: 34, text: "Page",
    text_size: 16, text_color: "#E4E8F0", chevron: "right", font: "montserrat", ...SHADOW } },
  slider: { label: "Brightness slider", defaults: { w: 200, h: 24, entity: "light.example", bg: "#3B4252", bar_color: "#F2CF66", knob_color: "#E4E8F0" } },
  image: { label: "Image", defaults: { w: 100, h: 100 } },
  label: { label: "Label", defaults: { text: "New label", text_size: 16, text_color: "#E4E8F0", font: "montserrat" } },
  icon: { label: "Icon", defaults: { icon: "star-outline", icon_size: 32, icon_color: "#D8DCE4" } },
  wifi: { label: "Wi-Fi icon", defaults: { icon_size: 24 } },
  conn: { label: "HA connection text", defaults: { text_size: 14, text_color: "#8F98AA", font: "montserrat" } },
};

const colour = (key, label) => ({ key, label, kind: "colour" });
const text = (key, label) => ({ key, label, kind: "text" });
const select = (key, label, options) => ({ key, label, kind: "select", options });
const icon = (key, label, optional) => ({ key, label, kind: "icon", optional });
const number = (key, label, min, max) => ({ key, label, kind: "number", min, max });
const textSize = (key, label) => ({ key, label, kind: "size", options: TEXT_SIZES, min: 8, max: 120 });
const iconSize = (label) => ({ key: "icon_size", label, kind: "size", options: ICON_SIZES, min: 8, max: 240 });
const entity = (...domains) => ({ key: "entity", label: "Entity", kind: "entity", domains });
const OFF_OPACITY = number("off_opacity", "Off opacity %", 0, 100);
const BOX = [number("radius", "Corners", 0, 240), colour("bg", "Background"), colour("border", "Border"),
  { key: "shadow_preset", label: "Shadow preset", kind: "shadow_preset" },
  number("shadow_width", "Shadow size", 0, 100), colour("shadow_color", "Shadow colour"), number("shadow_opa", "Shadow opacity %", 0, 100),
  number("shadow_offset_x", "Shadow X", -100, 100), number("shadow_offset_y", "Shadow Y", -100, 100), number("shadow_spread", "Shadow spread", -50, 50)];
const FONT_FIELD = select("font", "Font", Object.entries(FONTS).map(([value, f]) => [value, f[0]]));
const TEXT_STYLE = [FONT_FIELD, textSize("text_size", "Text size"), colour("text_color", "Text colour")];

const FIELDS = {
  toggle: [text("text", "Text"), entity("light", "switch", "fan", "input_boolean", "cover", "lock", "media_player", "climate"), icon("icon", "Icon", true), iconSize("Icon size"),
    { key: "show_state", label: "Lights up", kind: "bool" }, OFF_OPACITY, ...BOX, colour("bg_on", "When on"),
    colour("icon_color", "Icon colour"), colour("icon_color_on", "Icon when on"), ...TEXT_STYLE],
  sensor: [text("text", "Text"), entity("sensor", "number", "input_number"), icon("icon", "Icon"), iconSize("Icon size"),
    colour("icon_color", "Icon colour"), text("unit", "Unit"), number("decimals", "Decimals", 0, 3),
    textSize("value_size", "Value size"), colour("value_color", "Value colour"), ...BOX, ...TEXT_STYLE],
  status: [text("text", "Text"), entity(),
    text("on_state", "Good state"), text("on_text", "Good text"), icon("on_icon", "Good icon"), colour("on_color", "Good colour"),
    text("off_state", "Other state"), text("off_text", "Other text"), icon("off_icon", "Other icon"), colour("off_color", "Other colour"),
    iconSize("Icon size"), OFF_OPACITY, ...BOX, ...TEXT_STYLE],
  page_button: [text("text", "Text"), { key: "target", label: "Goes to", kind: "page" },
    select("chevron", "Arrow", ["right", "left", "none"]), ...BOX, ...TEXT_STYLE],
  slider: [entity("light"), colour("bg", "Track"), colour("bar_color", "Bar"), colour("knob_color", "Knob")],
  image: [{ key: "src", label: "File", kind: "image" }],
  label: [text("text", "Text"), ...TEXT_STYLE],
  icon: [icon("icon", "Icon"), iconSize("Size"), colour("icon_color", "Colour")],
  wifi: [iconSize("Size")],
  conn: TEXT_STYLE,
};

const $ = (id) => document.getElementById(id);
const make = (tag, className, textContent) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (textContent !== undefined) node.textContent = textContent;
  return node;
};

let design, designId, displays = {}, W = 480, H = 320;
let icons = {}, pageIndex = 0, selectedId = null, zoom = 1;
let undoStack = [], redoStack = [], saveTimer = null;
let shadowPresets = [], entities = [], entityStatus = "";
let live = {}, liveDrawn = "", dragging = false;

const page = () => design.pages[pageIndex];
const selected = () => page().elements.find((e) => e.id === selectedId) || null;
const glyph = (name) => (icons[name] ? String.fromCodePoint(parseInt(icons[name], 16)) : "");
const snap = (v) => ($("snap").checked ? Math.round(v / GRID) * GRID : Math.round(v));
const scaled = (h, offset, base) => Math.floor(offset * h / base + .5);

function uniqueId(prefix, taken) {
  let n = 1;
  while (taken.has(`${prefix}_${n}`)) n++;
  return `${prefix}_${n}`;
}
const allElementIds = () => new Set(design.pages.flatMap((p) => p.elements.map((e) => e.id)));

/* ---------- history and saving ---------- */

function commit() {
  const snapshot = JSON.stringify(design);
  if (undoStack.at(-1) === snapshot) return;
  undoStack.push(snapshot);
  redoStack = [];
  scheduleSave();
  updateHistoryButtons();
}

/* The top of undoStack is always the current design. */
function restore(snapshot) {
  design = JSON.parse(snapshot);
  pageIndex = Math.min(pageIndex, design.pages.length - 1);
  scheduleSave();
  renderAll();
}

function undo() {
  if (undoStack.length < 2) return;
  redoStack.push(undoStack.pop());
  restore(undoStack.at(-1));
}

function redo() {
  if (!redoStack.length) return;
  undoStack.push(redoStack.pop());
  restore(undoStack.at(-1));
}

function updateHistoryButtons() {
  $("undo").disabled = undoStack.length < 2;
  $("redo").disabled = !redoStack.length;
}

function scheduleSave() {
  $("status").textContent = "Saving";
  clearTimeout(saveTimer);
  saveTimer = setTimeout(save, 400);
}

async function save() {
  clearTimeout(saveTimer);
  saveTimer = null;
  try {
    const response = await fetch(`api/designs/${designId}`, { method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(design) });
    $("status").textContent = response.ok ? "Saved" : "Not saved";
  } catch {
    $("status").textContent = "Not saved";
  }
}

/* ---------- canvas ---------- */

function part(parent, className, content, y, size, color, isIcon) {
  const node = make("div", `part${isIcon ? " mdi" : ""}${className ? ` ${className}` : ""}`, content);
  node.style.marginTop = `${y}px`;
  node.style.fontSize = `${size}px`;
  if (color) node.style.color = color;
  parent.append(node);
}

function applyFont(node, e) {
  const [, family, weight] = FONTS[e.font];
  node.style.fontFamily = family;
  node.style.fontWeight = weight;
}

function drawTile(node, e) {
  const state = live[e.entity]?.state, known = state !== undefined;
  // Everything here follows the panel's own rules, in panel.yaml.j2
  const on = $("show-on").checked || (known && (e.type === "status" ? state === e.on_state : !NOT_ON.includes(state)));
  node.classList.add("tile");
  applyFont(node, e);
  node.style.borderRadius = `${e.radius}px`;
  node.style.borderColor = e.border;
  node.style.background = e.bg;
  if (e.shadow_width) {
    const alpha = Math.round(e.shadow_opa * 2.55).toString(16).padStart(2, "0");
    node.style.boxShadow = `${e.shadow_offset_x}px ${e.shadow_offset_y}px ${e.shadow_width}px ${e.shadow_spread}px ${e.shadow_color}${alpha}`;
  }
  if (!on && e.off_opacity !== undefined && (e.type === "status" || e.show_state)) node.style.opacity = e.off_opacity / 100;
  if (e.type === "toggle") {
    const lit = on && e.show_state;
    if (lit) node.style.background = e.bg_on;
    if (e.icon) {
      part(node, "", glyph(e.icon), scaled(e.h, -14, 102), e.icon_size, lit ? e.icon_color_on : e.icon_color, true);
      part(node, "", e.text, scaled(e.h, 24, 102), e.text_size, e.text_color);
    } else {
      part(node, "", e.text, 0, e.text_size, e.text_color);
    }
  } else if (e.type === "sensor") {
    part(node, "", glyph(e.icon), scaled(e.h, -28, 116), e.icon_size, e.icon_color, true);
    part(node, "", e.text, scaled(e.h, 6, 116), e.text_size, e.text_color);
    const reading = parseFloat(state);
    const value = Number.isNaN(reading) ? (e.decimals ? `--.${"-".repeat(e.decimals)}` : "--") : reading.toFixed(e.decimals);
    part(node, "", `${value}${e.unit}`, scaled(e.h, 32, 116), e.value_size, e.value_color);
  } else if (e.type === "status") {
    part(node, "", glyph(on ? e.on_icon : e.off_icon), scaled(e.h, -28, 116), e.icon_size, on ? e.on_color : e.off_color, true);
    part(node, "", e.text, scaled(e.h, 8, 116), e.text_size, e.text_color);
    const other = known && state !== e.off_state ? state : e.off_text;
    part(node, "", on ? e.on_text : other, scaled(e.h, 32, 116), 16, on ? e.on_color : e.off_color);
  } else if (e.type === "page_button") {
    const arrow = { left: `\u2039 ${e.text}`, right: `${e.text} \u203a` }[e.chevron] || e.text;
    part(node, "", arrow, 0, e.text_size, e.text_color);
  }
}

/* Shows 60% until Home Assistant reports the light. It has no brightness while the light is off. */
function drawSlider(node, e) {
  const light = live[e.entity], level = light ? Math.round((light.brightness ?? 0) / 2.55) : 60;
  const vertical = e.h > e.w, knobSize = Math.min(e.w, e.h) + 8;
  const track = make("div", "slider-track"), bar = make("div", "slider-bar"), knob = make("div", "slider-knob");
  track.style.background = e.bg;
  bar.style.background = e.bar_color;
  bar.style[vertical ? "height" : "width"] = `${level}%`;
  bar.style[vertical ? "width" : "height"] = "100%";
  knob.style.background = e.knob_color;
  knob.style.width = knob.style.height = `${knobSize}px`;
  knob.style.left = vertical ? "50%" : `${level}%`;
  knob.style.top = vertical ? `${100 - level}%` : "50%";
  track.append(bar);
  node.append(track, knob);
}

function drawImage(node, e) {
  const image = make("img");
  image.src = `images/${e.src}`;
  image.alt = "";
  node.append(image);
}

function drawElement(e) {
  const node = make("div", "el");
  node.dataset.id = e.id;
  if (SIZED.has(e.type)) {
    node.style.width = `${e.w}px`;
    node.style.height = `${e.h}px`;
    if (e.type === "slider") drawSlider(node, e);
    else if (e.type === "image") drawImage(node, e);
    else drawTile(node, e);
  } else if (e.type === "label") {
    node.textContent = e.text;
    applyFont(node, e);
    node.style.fontSize = `${e.text_size}px`;
    node.style.color = e.text_color;
  } else if (e.type === "icon" || e.type === "wifi") {
    node.classList.add("mdi");
    node.textContent = glyph(e.type === "wifi" ? "wifi" : e.icon);
    node.style.fontSize = `${e.icon_size}px`;
    node.style.color = e.type === "wifi" ? "#6BCB77" : e.icon_color;
  } else if (e.type === "conn") {
    node.textContent = "Home Assistant Connected";
    applyFont(node, e);
    node.style.fontSize = `${e.text_size}px`;
    node.style.color = e.text_color;
  }
  return node;
}

/* Where an element's top-left corner lands: LVGL aligns inside the screen, then offsets by x/y. */
function boxOf(e, node) {
  const [ax, ay] = ALIGNS[e.align];
  const w = node.offsetWidth, h = node.offsetHeight;
  return { left: (W - w) * ax + e.x, top: (H - h) * ay + e.y, w, h };
}

const nodeOf = (e) => $("lcd").querySelector(`[data-id="${CSS.escape(e.id)}"]`);

function place(e, node) {
  const box = boxOf(e, node);
  node.style.left = `${box.left}px`;
  node.style.top = `${box.top}px`;
}

function drawCanvas() {
  const lcd = $("lcd");
  lcd.replaceChildren();
  lcd.style.background = page().bg;
  for (const e of page().elements) {
    const node = drawElement(e);
    lcd.append(node);
    place(e, node);
    if (e.id === selectedId) {
      node.classList.add("selected");
      if (SIZED.has(e.type)) {
        for (const corner of ["nw", "ne", "sw", "se"]) {
          const handle = make("div", `handle ${corner}`);
          handle.dataset.corner = corner;
          node.append(handle);
        }
      }
    }
    node.addEventListener("pointerdown", (event) => startDrag(event, e, node));
  }
}

function startDrag(event, e, node) {
  event.stopPropagation();
  event.preventDefault();
  document.activeElement?.blur();
  if (selectedId !== e.id) {
    selectedId = e.id;
    renderAll();
    // Redrawing replaced the node, so keep dragging its replacement
    node = nodeOf(e);
  }
  const corner = event.target.dataset?.corner;
  const start = { px: event.clientX, py: event.clientY, x: e.x, y: e.y, w: e.w, h: e.h };
  const box = boxOf(e, node);

  if (corner && e.align !== "TOP_LEFT") {
    // Resizing is simplest from the top-left, so switch to that without moving the tile
    e.align = "TOP_LEFT";
    start.x = e.x = Math.round(box.left);
    start.y = e.y = Math.round(box.top);
  }

  const lcd = $("lcd");
  dragging = true;
  lcd.setPointerCapture(event.pointerId);
  const move = (m) => {
    const dx = (m.clientX - start.px) / zoom, dy = (m.clientY - start.py) / zoom;
    if (corner) {
      resize(e, start, corner, dx, dy);
      node.style.width = `${e.w}px`;
      node.style.height = `${e.h}px`;
    } else {
      // Up to one screen past each edge, and snap the position you see rather than the offset
      const left = clamp(snap(box.left + dx), -W, 2 * W - box.w);
      const top = clamp(snap(box.top + dy), -H, 2 * H - box.h);
      e.x = Math.round(start.x + left - box.left);
      e.y = Math.round(start.y + top - box.top);
    }
    place(e, node);
    syncGeometryFields(e);
  };
  const end = () => {
    dragging = false;
    lcd.removeEventListener("pointermove", move);
    lcd.removeEventListener("pointerup", end);
    lcd.removeEventListener("pointercancel", end);
    commit();
    renderAll();
  };
  lcd.addEventListener("pointermove", move);
  lcd.addEventListener("pointerup", end);
  lcd.addEventListener("pointercancel", end);
}

function resize(e, start, corner, dx, dy) {
  const right = start.x + start.w, bottom = start.y + start.h;
  if (corner.includes("e")) e.w = clamp(snap(start.w + dx), MIN_SIZE, 2 * W);
  if (corner.includes("s")) e.h = clamp(snap(start.h + dy), MIN_SIZE, 2 * H);
  if (corner.includes("w")) {
    e.x = clamp(snap(start.x + dx), Math.max(-W, right - 2 * W), right - MIN_SIZE);
    e.w = right - e.x;
  }
  if (corner.includes("n")) {
    e.y = clamp(snap(start.y + dy), Math.max(-H, bottom - 2 * H), bottom - MIN_SIZE);
    e.h = bottom - e.y;
  }
}

/* ---------- panels ---------- */

function drawTabs() {
  $("tabs").replaceChildren(...design.pages.map((p, i) => {
    const tab = make("button", `tab${i === pageIndex ? " on" : ""}`, p.name);
    if (i === pageIndex) tab.setAttribute("aria-current", "page");
    tab.addEventListener("click", () => {
      pageIndex = i;
      selectedId = null;
      renderAll();
      $("tabs").querySelector(".on")?.focus();
    });
    return tab;
  }));
}

function elementName(e) {
  return e.text || TYPES[e.type].label;
}

function drawElementList() {
  $("elements").replaceChildren(...page().elements.map((e) => {
    const item = make("li");
    const button = make("button", e.id === selectedId ? "on" : "", elementName(e));
    button.title = TYPES[e.type].label;
    button.addEventListener("click", () => {
      selectedId = e.id;
      renderAll();
      $("elements").querySelector("button.on")?.focus();
    });
    item.append(button);
    return item;
  }));
}

function field(labelText, control) {
  const row = make("label", "field");
  row.append(make("span", "", labelText), control);
  return row;
}

/* Typing redraws live; leaving the field records one undo step. */
function bind(input, read, apply) {
  input.addEventListener("input", () => { apply(read()); drawCanvas(); drawElementList(); drawTabs(); });
  input.addEventListener("change", commit);
}

function numberInput(obj, key, min, max) {
  const input = make("input");
  input.type = "number";
  input.value = obj[key];
  input.dataset.key = key;
  input.setAttribute("aria-label", key.toUpperCase());
  if (min !== undefined) input.min = min;
  if (max !== undefined) input.max = max;
  bind(input, () => input.value, (v) => {
    if (v !== "" && Number.isInteger(+v)) obj[key] = +v;
  });
  return input;
}

function iconField(e, f) {
  const wrap = make("div");
  const current = make("div", "icon-current");
  const preview = make("i", "mdi", glyph(e[f.key]));
  const name = make("span", "", e[f.key] || "none");
  current.append(preview, name);
  const search = make("input", "icon-search");
  search.type = "search";
  search.placeholder = `Search ${Object.keys(icons).length} icons`;
  search.setAttribute("aria-label", `Search for ${f.label}`);
  const grid = make("div", "icon-grid");
  grid.hidden = true;
  const choose = (value) => {
    e[f.key] = value;
    commit();
    renderAll();
  };
  let shown = ICON_PAGE;
  const drawGrid = () => {
    // Home Assistant writes icons as mdi:name
    const words = search.value.toLowerCase().replaceAll("mdi:", "").split(/\s+/).filter(Boolean);
    const matches = Object.keys(icons).filter((n) => words.every((w) => n.includes(w)));
    grid.hidden = false;
    grid.replaceChildren(...matches.slice(0, shown).map((n) => {
      const button = make("button", "mdi", glyph(n));
      button.type = "button";
      button.title = n;
      button.setAttribute("aria-label", n);
      button.addEventListener("click", () => choose(n));
      return button;
    }));
    if (!matches.length) grid.append(make("p", "hint wide", "No icons match."));
    if (matches.length > shown) {
      const more = make("button", "wide", `Show more (${matches.length - shown} left)`);
      more.type = "button";
      more.addEventListener("click", () => { shown += ICON_PAGE; drawGrid(); });
      grid.append(more);
    }
  };
  search.addEventListener("focus", drawGrid);
  search.addEventListener("input", () => { shown = ICON_PAGE; drawGrid(); });
  wrap.append(current, search);
  if (f.optional) {
    const none = make("button", "", "No icon");
    none.type = "button";
    none.addEventListener("click", () => choose(""));
    wrap.append(none);
  }
  const row = make("div", "field");
  row.append(make("span", "", f.label), wrap);
  const box = make("div");
  box.append(row, grid);
  return box;
}

function entityField(e, f) {
  const input = make("input");
  input.value = e[f.key];
  bind(input, () => input.value, (v) => { e[f.key] = v; });
  const box = make("div");
  box.append(field(f.label, input));
  if (!entities.length) return box;
  const list = make("datalist");
  list.id = "entity-list";
  list.append(...entities.filter((en) => !f.domains.length || f.domains.includes(en.id.split(".")[0])).map((en) => {
    const option = make("option");
    option.value = en.id;
    option.label = en.name;
    return option;
  }));
  input.setAttribute("list", list.id);
  const missing = make("p", "hint", "Not found in Home Assistant.");
  const check = () => { missing.hidden = entities.some((en) => en.id === e[f.key]); };
  // Part-typed IDs aren't mistakes, so only warn after leaving the box
  input.addEventListener("input", () => { missing.hidden = true; });
  input.addEventListener("change", check);
  check();
  box.append(list, missing);
  return box;
}

function shadowPresetField(e) {
  const input = make("select");
  const add = (value, labelText) => {
    const option = make("option", "", labelText);
    option.value = value;
    input.append(option);
  };
  add("none", "No shadow");
  for (const p of shadowPresets) add(p.id, `#${p.id}: blur ${p.shadow_width}, ${p.shadow_opa}%${p.simplified ? " (simplified)" : ""}`);
  const match = shadowPresets.find((p) => SHADOW_KEYS.every((k) => p[k] === e[k]));
  if (e.shadow_width && !match) add("custom", "Custom");
  input.value = !e.shadow_width ? "none" : match ? match.id : "custom";
  input.addEventListener("change", () => {
    if (input.value === "none") e.shadow_width = 0;
    else if (input.value !== "custom") Object.assign(e, ...SHADOW_KEYS.map((k) => ({ [k]: shadowPresets.find((p) => `${p.id}` === input.value)[k] })));
    commit();
    renderAll();
    $("shadow-preset").focus();  // so the arrow keys can step through the presets
  });
  input.id = "shadow-preset";
  return field("Shadow preset", input);
}

function imageField(e) {
  const replace = make("button", "", "Replace");
  replace.type = "button";
  replace.addEventListener("click", async () => {
    const picked = await pickImage();
    if (!picked) return;
    e.src = picked.src;
    commit();
    renderAll();
  });
  const box = make("div");
  // The most it can use: 2 bytes a pixel, plus 1 for transparency in a PNG
  const kb = Math.ceil(e.w * e.h * (e.src.endsWith(".png") ? 3 : 2) / 1024);
  box.append(field("File", replace), make("p", "hint", `Uses up to ${kb} KB of flash on the panel.`));
  return box;
}

/* Suggests the usual sizes, and takes any other that's typed. */
function sizeField(e, f) {
  const input = numberInput(e, f.key, f.min, f.max);
  input.setAttribute("aria-label", f.label);
  input.title = `Pick a size or type one from ${f.min} to ${f.max}. Bigger sizes use more flash on the panel.`;
  const list = make("datalist");
  list.id = `sizes-${f.key}`;
  list.append(...f.options.map((size) => {
    const option = make("option");
    option.value = size;
    return option;
  }));
  input.setAttribute("list", list.id);
  const row = field(f.label, input);
  row.append(list);
  return row;
}

function control(e, f) {
  if (f.kind === "icon") return iconField(e, f);
  if (f.kind === "entity") return entityField(e, f);
  if (f.kind === "shadow_preset") return shadowPresetField(e);
  if (f.kind === "image") return imageField(e);
  if (f.kind === "size") return sizeField(e, f);
  let input;
  if (f.kind === "number") {
    input = numberInput(e, f.key, f.min, f.max);
  } else if (f.kind === "bool") {
    input = make("input");
    input.type = "checkbox";
    input.checked = e[f.key];
    bind(input, () => input.checked, (v) => { e[f.key] = v; });
  } else if (f.kind === "select" || f.kind === "page") {
    input = make("select");
    const options = f.kind === "page"
      ? design.pages.map((p) => [p.id, p.name])
      : f.options.map((o) => (Array.isArray(o) ? o : [o, o]));
    for (const [value, labelText] of options) {
      const option = make("option", "", labelText);
      option.value = value;
      input.append(option);
    }
    input.value = e[f.key];
    bind(input, () => input.value, (v) => { e[f.key] = typeof e[f.key] === "number" ? +v : v; });
  } else {
    input = make("input");
    input.type = f.kind === "colour" ? "color" : "text";
    input.value = f.kind === "colour" ? e[f.key].toLowerCase() : e[f.key];
    bind(input, () => input.value, (v) => { e[f.key] = f.kind === "colour" ? v.toUpperCase() : v; });
  }
  return field(f.label, input);
}

function changeAlign(e, align) {
  // Keep the element where it is on screen when its anchor changes
  const box = boxOf(e, nodeOf(e));
  const [ax, ay] = ALIGNS[align];
  e.align = align;
  e.x = Math.round(box.left - (W - box.w) * ax);
  e.y = Math.round(box.top - (H - box.h) * ay);
  commit();
  renderAll();
}

function syncGeometryFields(e) {
  for (const key of ["x", "y", "w", "h"]) {
    const input = document.querySelector(`#props input[data-key="${key}"]`);
    if (input && e[key] !== undefined) input.value = e[key];
  }
}

function drawElementProps(e) {
  const props = $("props");
  props.replaceChildren(make("h2", "", TYPES[e.type].label));
  if (e.type === "wifi") props.append(make("p", "hint", "Green when connected, red when not."));
  if (e.type === "conn") props.append(make("p", "hint", "Shows whether Home Assistant is connected."));

  const position = make("div", "pair");
  position.append(numberInput(e, "x", -2 * W, 2 * W), numberInput(e, "y", -2 * H, 2 * H));
  props.append(field("X / Y", position));
  if (SIZED.has(e.type)) {
    const size = make("div", "pair");
    size.append(numberInput(e, "w", 10, 2 * W), numberInput(e, "h", 10, 2 * H));
    props.append(field("W / H", size));
  }
  const align = make("select");
  for (const name of Object.keys(ALIGNS)) {
    const option = make("option", "", name.replace("_", " ").toLowerCase());
    option.value = name;
    align.append(option);
  }
  align.value = e.align;
  align.addEventListener("change", () => changeAlign(e, align.value));
  props.append(field("Anchor", align));

  const list = page().elements, at = list.indexOf(e);
  const layers = make("div", "layers");
  for (const [label, to] of [["To front", list.length - 1], ["Forward", at + 1], ["Backward", at - 1], ["To back", 0]]) {
    const button = make("button", "", label);
    button.dataset.layer = label;
    button.disabled = to === at || to < 0 || to >= list.length;
    button.addEventListener("click", () => moveLayer(e, to, label));
    layers.append(button);
  }
  const layer = make("div", "field");
  layer.append(make("span", "", "Layer"), layers);
  props.append(layer);

  for (const f of FIELDS[e.type]) props.append(control(e, f));
  if (e.shadow_width && design.display === "waveshare_35") {
    props.append(make("p", "hint", "Shadows can make this panel redraw slowly, as it has no PSRAM. Check it on the real screen."));
  }

  const actions = make("div", "actions");
  const duplicate = make("button", "", "Duplicate");
  duplicate.addEventListener("click", duplicateSelected);
  const remove = make("button", "danger", "Delete");
  remove.addEventListener("click", deleteSelected);
  actions.append(duplicate, remove);
  props.append(actions);
}

function setTheme(key, value) {
  design.theme[key] = value;
  for (const p of design.pages) {
    if (key === "page_bg") p.bg = value;
    for (const e of p.elements) applyTheme(e, key);
  }
}

function applyTheme(e, key) {
  for (const target of THEME_TARGETS[key] || []) {
    if (target in e) e[target] = design.theme[key];
  }
}

function drawThemeProps(props) {
  props.append(make("h2", "", "Theme"));
  props.append(make("p", "hint", "Changes everything in this design, and new elements follow it. You can still change single elements afterwards."));
  for (const [key, label, fallback] of THEME_COLOURS) {
    const input = make("input");
    input.type = "color";
    input.value = (design.theme[key] ?? fallback).toLowerCase();
    bind(input, () => input.value, (v) => setTheme(key, v.toUpperCase()));
    props.append(field(label, input));
  }
  const font = make("select");
  for (const [value, f] of Object.entries(FONTS)) {
    const option = make("option", "", f[0]);
    option.value = value;
    font.append(option);
  }
  font.value = design.theme.font ?? "montserrat";
  bind(font, () => font.value, (v) => setTheme("font", v));
  props.append(field("Font", font));
  const corners = make("input");
  corners.type = "number";
  corners.min = 0;
  corners.max = 240;
  corners.value = design.theme.radius ?? 12;
  bind(corners, () => corners.value, (v) => {
    if (v !== "" && Number.isInteger(+v)) setTheme("radius", +v);
  });
  props.append(field("Corners", corners));
}

function drawPageProps() {
  const props = $("props");
  const p = page();
  props.replaceChildren(make("h2", "", "Page"));
  const name = make("input");
  name.value = p.name;
  bind(name, () => name.value, (v) => { p.name = v; });
  props.append(field("Name", name));
  const bg = make("input");
  bg.type = "color";
  bg.value = p.bg.toLowerCase();
  bind(bg, () => bg.value, (v) => { p.bg = v.toUpperCase(); });
  props.append(field("Background", bg));
  const remove = make("button", "danger", "Delete page");
  remove.disabled = design.pages.length < 2;
  remove.addEventListener("click", deletePage);
  const actions = make("div", "actions");
  actions.append(remove);
  props.append(actions);

  drawThemeProps(props);

  props.append(make("h2", "", "Device"));
  const device = make("input");
  device.value = design.device.name;
  bind(device, () => device.value, (v) => { design.device.name = v; });
  props.append(field("Name", device));
  const friendly = make("input");
  friendly.value = design.device.friendly_name;
  bind(friendly, () => friendly.value, (v) => {
    design.device.friendly_name = v;
    $("design-select").selectedOptions[0].textContent = v;
  });
  props.append(field("Friendly name", friendly));
  props.append(field("Display", make("span", "", displays[design.display].label)));
  props.append(make("p", "hint", "Keep the device name the same as the panel you flashed, or Home Assistant sees a new device."));
  props.append(make("p", "hint", "Click an element to edit it. Drag to move. Arrow keys nudge it by 1px, or 10px with Shift."));
  props.append(make("p", "hint", entityStatus));
  const removeDesign = make("button", "danger", "Delete design");
  removeDesign.disabled = $("design-select").options.length < 2;
  removeDesign.addEventListener("click", deleteDesign);
  const designActions = make("div", "actions");
  designActions.append(removeDesign);
  props.append(designActions);
}

function drawProps() {
  const e = selected();
  if (e) drawElementProps(e);
  else drawPageProps();
}

function renderAll() {
  drawTabs();
  drawCanvas();
  drawElementList();
  drawProps();
  updateHistoryButtons();
}

/* ---------- actions ---------- */

function pickImage() {
  return new Promise((resolve) => {
    const input = make("input");
    input.type = "file";
    input.accept = "image/png,image/jpeg";
    input.addEventListener("change", async () => {
      const file = input.files[0];
      const response = await fetch("api/images", { method: "POST", headers: { "Content-Type": file.type || "application/octet-stream" }, body: file });
      const result = await response.json().catch(() => ({ errors: ["Images can be up to 5 MB."] }));
      if (!response.ok) {
        alert(result.errors[0]);
        resolve(null);
        return;
      }
      const image = new Image();
      image.src = `images/${result.src}`;
      await image.decode();
      resolve({ src: result.src, width: image.naturalWidth, height: image.naturalHeight });
    });
    input.addEventListener("cancel", () => resolve(null));
    input.click();
  });
}

async function addImage(x, y) {
  const picked = await pickImage();
  if (!picked) return;
  // Start at no more than half the screen, and never bigger than the file
  const scale = Math.min(1, W / 2 / picked.width, H / 2 / picked.height);
  addElement("image", x, y, { src: picked.src, w: Math.max(MIN_SIZE, Math.round(picked.width * scale)),
    h: Math.max(MIN_SIZE, Math.round(picked.height * scale)) });
}

function addElement(type, x, y, extra) {
  if (type === "image" && !extra) {
    addImage(x, y);
    return;
  }
  const defaults = { ...structuredClone(TYPES[type].defaults), ...extra };
  const size = { w: defaults.w || 100, h: defaults.h || 30 };
  const e = { id: uniqueId(type, allElementIds()), type, align: "TOP_LEFT", ...defaults };
  e.x = snap(Math.max(0, Math.min(W - size.w, x ?? (W - size.w) / 2)));
  e.y = snap(Math.max(0, Math.min(H - size.h, y ?? (H - size.h) / 2)));
  if (type === "page_button") {
    const other = design.pages.find((p) => p !== page()) || page();
    e.target = other.id;
    e.text = other.name;
  }
  for (const key of Object.keys(design.theme)) applyTheme(e, key);
  page().elements.push(e);
  selectedId = e.id;
  commit();
  renderAll();
}

function duplicateSelected() {
  const e = selected();
  if (!e) return;
  const copy = structuredClone(e);
  copy.id = uniqueId(e.type, allElementIds());
  copy.x += 12;
  copy.y += 12;
  page().elements.push(copy);
  selectedId = copy.id;
  commit();
  renderAll();
}

/* The list order is the drawing order, here and on the panel: later elements cover earlier ones. */
function moveLayer(e, to, label) {
  const list = page().elements;
  list.splice(to, 0, ...list.splice(list.indexOf(e), 1));
  commit();
  renderAll();
  $("props").querySelector(`.layers [data-layer="${label}"]`)?.focus();
}

function deleteSelected() {
  page().elements = page().elements.filter((e) => e.id !== selectedId);
  selectedId = null;
  commit();
  renderAll();
}

function addPage() {
  const id = uniqueId("page", new Set(design.pages.map((p) => p.id)));
  const from = page();
  const name = `Page ${design.pages.length + 1}`;
  const taken = allElementIds();
  const title = { id: uniqueId("label", taken), type: "label", align: "TOP_LEFT", x: 16, y: 14,
    text: name, text_size: 24, text_color: "#FFFFFF", font: "montserrat" };
  taken.add(title.id);
  const back = { id: uniqueId("page_button", taken), type: "page_button", align: "TOP_RIGHT", x: -16, y: 10,
    ...TYPES.page_button.defaults, text: from.name, chevron: "left", target: from.id };
  taken.add(back.id);
  // Every page needs a way in, or it can never be reached on the panel
  const link = { id: uniqueId("page_button", taken), type: "page_button", align: "TOP_LEFT", x: (W - 144) / 2, y: H - 44,
    ...TYPES.page_button.defaults, text: name, chevron: "right", target: id };
  for (const key of Object.keys(design.theme)) [title, back, link].forEach((e) => applyTheme(e, key));
  from.elements.push(link);
  design.pages.push({ id, name, bg: design.theme.page_bg ?? "#1E222B", elements: [title, back] });
  pageIndex = design.pages.length - 1;
  selectedId = null;
  commit();
  renderAll();
}

function deletePage() {
  const p = page();
  if (design.pages.length < 2 || !confirm(`Delete the page "${p.name}" and everything on it?`)) return;
  design.pages.splice(pageIndex, 1);
  // Buttons that pointed at it would have nowhere to go
  for (const other of design.pages) {
    other.elements = other.elements.filter((e) => !(e.type === "page_button" && e.target === p.id));
  }
  pageIndex = Math.max(0, pageIndex - 1);
  selectedId = null;
  commit();
  renderAll();
}

function nudge(e, dx, dy) {
  e.x += dx;
  e.y += dy;
  commit();
  renderAll();
}

/* ---------- YAML dialog ---------- */

async function showYaml() {
  const errors = $("yaml-errors"), area = $("yaml-text");
  errors.replaceChildren();
  area.value = "";
  $("yaml-dialog").showModal();
  try {
    const response = await fetch("api/yaml", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(design) });
    const result = await response.json();
    if (result.errors) errors.replaceChildren(...result.errors.map((m) => make("li", "", m)));
    area.value = result.yaml || "";
  } catch {
    errors.replaceChildren(make("li", "", "Couldn't reach the server."));
  }
  const ready = area.value !== "";
  area.hidden = !ready;
  document.querySelector(".dialog-foot").hidden = !ready;
}

async function copyYaml() {
  const area = $("yaml-text"), button = $("copy-yaml");
  try {
    await navigator.clipboard.writeText(area.value);
  } catch {
    // The clipboard API needs HTTPS; this fallback works over plain HTTP on a LAN
    area.select();
    document.execCommand("copy");
  }
  button.textContent = "Copied";
  setTimeout(() => { button.textContent = "Copy"; }, 1500);
}

function downloadYaml() {
  const link = make("a");
  link.href = URL.createObjectURL(new Blob([$("yaml-text").value], { type: "text/yaml" }));
  link.download = `${design.device.name}.yaml`;
  link.click();
  URL.revokeObjectURL(link.href);
}

/* ---------- start-up ---------- */

function buildPalette() {
  $("palette").replaceChildren(...Object.entries(TYPES).map(([type, info]) => {
    const chip = make("button", "chip", info.label);
    chip.draggable = true;
    chip.addEventListener("click", () => addElement(type));
    chip.addEventListener("dragstart", (event) => event.dataTransfer.setData("text/plain", type));
    return chip;
  }));
  const lcd = $("lcd");
  lcd.addEventListener("dragover", (event) => event.preventDefault());
  lcd.addEventListener("drop", (event) => {
    event.preventDefault();
    const type = event.dataTransfer.getData("text/plain");
    if (!TYPES[type]) return;
    const rect = lcd.getBoundingClientRect();
    addElement(type, (event.clientX - rect.left) / zoom, (event.clientY - rect.top) / zoom);
  });
}

function applyZoom() {
  zoom = +$("zoom").value;
  $("lcd").style.width = `${W}px`;
  $("lcd").style.height = `${H}px`;
  $("lcd").style.transform = `scale(${zoom})`;
  $("lcd-frame").style.width = `${W * zoom}px`;
  $("lcd-frame").style.height = `${H * zoom}px`;
}

function wireEvents() {
  $("add-page").addEventListener("click", addPage);
  $("design-select").addEventListener("change", () => loadDesign(+$("design-select").value));
  $("new-design").addEventListener("click", () => $("new-design-dialog").showModal());
  $("close-new-design").addEventListener("click", () => $("new-design-dialog").close());
  $("create-design").addEventListener("click", createDesign);
  $("undo").addEventListener("click", undo);
  $("redo").addEventListener("click", redo);
  $("show-on").addEventListener("change", drawCanvas);
  $("zoom").addEventListener("change", applyZoom);
  $("get-yaml").addEventListener("click", showYaml);
  $("close-yaml").addEventListener("click", () => $("yaml-dialog").close());
  $("copy-yaml").addEventListener("click", copyYaml);
  $("download-yaml").addEventListener("click", downloadYaml);
  // Clicking empty screen goes back to the page settings
  $("lcd").addEventListener("pointerdown", () => { selectedId = null; renderAll(); });

  document.addEventListener("keydown", (event) => {
    if (event.target.closest("input, select, textarea, dialog")) return;
    const key = event.key.toLowerCase(), ctrl = event.ctrlKey || event.metaKey;
    if (ctrl && key === "z") { event.preventDefault(); event.shiftKey ? redo() : undo(); return; }
    if (ctrl && key === "y") { event.preventDefault(); redo(); return; }
    const e = selected();
    if (!e) return;
    const step = event.shiftKey ? 10 : 1;
    const moves = { arrowleft: [-step, 0], arrowright: [step, 0], arrowup: [0, -step], arrowdown: [0, step] };
    if (moves[key]) { event.preventDefault(); nudge(e, ...moves[key]); }
    else if (key === "delete" || key === "backspace") { event.preventDefault(); deleteSelected(); }
    else if (ctrl && key === "d") { event.preventDefault(); duplicateSelected(); }
    else if (key === "escape") { selectedId = null; renderAll(); }
  });
}

async function refreshDesignList(selected) {
  const list = await (await fetch("api/designs")).json();
  $("design-select").replaceChildren(...list.map((d) => {
    const option = make("option", "", d.name);
    option.value = d.id;
    return option;
  }));
  return list.some((d) => d.id === selected) ? selected : list[0].id;
}

async function loadDesign(id) {
  if (saveTimer) await save();  // don't lose edits made just before switching
  design = await (await fetch(`api/designs/${id}`)).json();
  design.theme ??= {};
  designId = id;
  localStorage.setItem("swpanel-design", id);
  $("design-select").value = id;
  ({ width: W, height: H } = displays[design.display]);
  pageIndex = 0;
  selectedId = null;
  undoStack = [JSON.stringify(design)];
  redoStack = [];
  $("status").textContent = "";
  $("zoom").value = W + 48 > $("lcd-frame").parentElement.clientWidth ? "0.75" : "1";
  applyZoom();
  renderAll();
}

async function createDesign() {
  const response = await fetch("api/designs", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ display: $("new-design-display").value }) });
  const { id } = await response.json();
  $("new-design-dialog").close();
  await refreshDesignList(id);
  await loadDesign(id);
}

async function deleteDesign() {
  if (!confirm(`Delete the design "${design.device.friendly_name}" and all its pages?`)) return;
  clearTimeout(saveTimer);
  saveTimer = null;
  await fetch(`api/designs/${designId}`, { method: "DELETE" });
  await loadDesign(await refreshDesignList(null));
}

/* Runs after the page is up, as a slow or missing Home Assistant shouldn't hold it back. */
async function loadEntities() {
  let ok = false, result = { configured: true, entities: [] };
  try {
    const response = await fetch("api/ha/entities");
    result = await response.json();
    ok = response.ok;
  } catch { /* Home Assistant or the app is restarting, so try again on the next poll */ }
  if (ok) entities = result.entities;  // keep the suggestions through a brief outage
  live = ok ? Object.fromEntries(entities.map((en) => [en.id, en])) : {};
  const status = !result.configured ? "Set HA_URL and HA_TOKEN to pick entities from a list."
    : ok ? `Home Assistant: ${entities.length} entities, live.`
      : "Couldn't reach Home Assistant. Check HA_URL and HA_TOKEN.";
  if (status !== entityStatus && !$("props").contains(document.activeElement)) {
    entityStatus = status;
    drawProps();
  }
  // Redrawing would take the element out from under a drag, and most changes aren't on this page
  const shown = JSON.stringify(page().elements.map((e) => live[e.entity] ?? null));
  if (shown !== liveDrawn && !dragging) {
    liveDrawn = shown;
    drawCanvas();
  }
  return result.configured;
}

/* Polling, as the browser never sees the token. A websocket through the server if 3s feels slow. */
async function pollEntities() {
  if (!document.hidden && !(await loadEntities())) return;
  setTimeout(pollEntities, LIVE_MS);
}

async function start() {
  const [displayResponse, iconResponse, presetResponse] = await Promise.all([fetch("api/displays"),
    fetch("static/vendor/mdi/icons.json"), fetch("static/shadow_presets.json")]);
  displays = await displayResponse.json();
  icons = await iconResponse.json();
  shadowPresets = (await presetResponse.json()).map(([id, simplified, ...values]) => ({ id, simplified,
    ...Object.fromEntries(["shadow_width", "shadow_color", "shadow_opa", "shadow_offset_x", "shadow_offset_y", "shadow_spread"].map((k, i) => [k, values[i]])) }));
  $("new-design-display").replaceChildren(...Object.entries(displays).map(([value, d]) => {
    const option = make("option", "", `${d.label} (${d.width}x${d.height})`);
    option.value = value;
    return option;
  }));
  buildPalette();
  wireEvents();
  // Text and icons size themselves from fonts that load after the first draw
  document.fonts.addEventListener("loadingdone", drawCanvas);
  await loadDesign(await refreshDesignList(+localStorage.getItem("swpanel-design")));
  await pollEntities();
}

start();
