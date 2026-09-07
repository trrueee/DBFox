// One browser renderer serves editing, immutable Artifact preview and HTML export.
// Browser HTML layout owns CJK/emoji shaping and wrapping; no text measurement copy.
export function renderPage(page, { showNotes = false } = {}) {
  const NS = "http://www.w3.org/2000/svg";
  const node = (name, attrs = {}, text) => {
    const value = document.createElementNS(NS, name);
    for (const [key, content] of Object.entries(attrs)) value.setAttribute(key, String(content));
    if (text !== undefined) value.textContent = text;
    return value;
  };
  const svg = node("svg", { xmlns: NS, width: page.width, height: page.height, viewBox: `0 0 ${page.width} ${page.height}`, role: "img", "aria-label": page.title });
  svg.append(node("title", {}, page.title), node("rect", { width: page.width, height: page.height, fill: page.background }));
  for (const panel of page.panels) {
    const x = panel.rect.x * page.width, y = panel.rect.y * page.height;
    const width = panel.rect.width * page.width, height = panel.rect.height * page.height;
    const g = node("svg", { x, y, width, height, viewBox: `0 0 ${width} ${height}`, overflow: "hidden", "data-object-id": panel.id, "data-object-kind": "panel" });
    g.append(node("title", {}, `${panel.title} · ${panel.shot.framing} · ${panel.shot.description}`));
    g.append(node("rect", { width, height, fill: panel.background, stroke: "#25323A", "stroke-width": 3 }));
    for (const element of panel.elements) {
      if (element.kind === "note" && !showNotes) continue;
      const r = element.rect, ex = r.x * width, ey = r.y * height, ew = r.width * width, eh = r.height * height;
      const item = node("g", { "data-object-id": element.id, "data-object-kind": element.kind });
      item.append(node("title", {}, element.kind === "character" ? element.label : element.text));
      if (element.kind === "character") {
        const cx = ex + ew / 2, hy = ey + eh * 0.16, body = ey + eh * 0.32;
        const head = Math.min(ew * 0.23, eh * 0.12);
        item.append(node("circle", { cx, cy: hy, r: head, fill: element.color, stroke: "#24333C", "stroke-width": 1.5 }));
        item.append(node("path", { d: `M${cx},${body} L${cx},${ey + eh * .65} M${cx},${body + eh * .08} L${ex + ew * .12},${ey + eh * (element.pose === "reaching" ? .18 : .58)} M${cx},${body + eh * .08} L${ex + ew * .88},${ey + eh * .58} ${element.pose === "seated" ? `M${cx},${ey + eh * .65} L${ex + ew * .85},${ey + eh * .65} L${ex + ew * .85},${ey + eh * .9} M${cx},${ey + eh * .65} L${ex + ew * .15},${ey + eh * .65} L${ex + ew * .15},${ey + eh * .9}` : `M${cx},${ey + eh * .65} L${ex + ew * .25},${ey + eh * .93} M${cx},${ey + eh * .65} L${ex + ew * .8},${ey + eh * (element.pose === "walking" ? .8 : .93)}`}`,
          stroke: element.color, "stroke-width": Math.max(4, ew * .13), "stroke-linecap": "round", fill: "none" }));
        if (element.facing !== "front") item.append(node("circle", { cx: cx + (element.facing === "left" ? -1 : 1) * head * .5, cy: hy - head * .1, r: Math.max(1, head * .13), fill: "#FFFFFF" }));
        item.append(node("text", { x: cx, y: ey + eh - 2, "text-anchor": "middle", "font-size": Math.min(16, ew / 5), "font-family": "sans-serif", fill: "#25323A" }, element.label));
      } else {
        if (element.kind === "bubble") {
          item.append(node("path", { d: `M${ex + ew * .4},${ey + eh * .7} L${element.tail_x * width},${element.tail_y * height} L${ex + ew * .65},${ey + eh * .7} Z`, fill: "#FFFFFF", stroke: "#25323A", "stroke-width": 2 }));
          item.append(node("rect", { x: ex, y: ey, width: ew, height: eh, rx: element.style === "shout" ? 3 : Math.min(ew, eh) * .24,
            fill: "#FFFFFF", stroke: "#25323A", "stroke-width": element.style === "shout" ? 3 : 2,
            ...(element.style === "thought" ? { "stroke-dasharray": "5 3" } : {}) }));
        } else item.append(node("rect", { x: ex, y: ey, width: ew, height: eh, rx: 2, fill: element.kind === "note" ? "#FFF5B4" : element.color, stroke: "#25323A", "stroke-width": 1.5 }));
        const foreign = node("foreignObject", { x: ex, y: ey, width: ew, height: eh, "pointer-events": "none" });
        const div = document.createElementNS("http://www.w3.org/1999/xhtml", "div");
        div.setAttribute("style", `box-sizing:border-box;width:100%;height:100%;padding:8px;overflow:hidden;white-space:pre-wrap;overflow-wrap:anywhere;font:${element.font_size || 16}px/1.3 "Segoe UI","Microsoft YaHei",sans-serif;color:#1C2931;`);
        div.textContent = element.text; foreign.append(div); item.append(foreign);
      }
      g.append(item);
    }
    svg.append(g);
  }
  return svg;
}
