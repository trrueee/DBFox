/**
 * Position short-lived overlays without a style attribute.  The values are
 * normalized before being written to a constructable stylesheet, so event
 * data cannot become arbitrary CSS.  This keeps a strict `style-src-attr
 * 'none'` CSP while retaining pixel-accurate context menus.
 */
const MAX_VIEWPORT_COORDINATE = 100_000;

let dynamicSheet: CSSStyleSheet | null = null;

function normalizedCoordinate(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.min(MAX_VIEWPORT_COORDINATE, Math.max(0, Math.round(value)));
}

function getDynamicSheet(): CSSStyleSheet | null {
  if (dynamicSheet) return dynamicSheet;
  if (typeof document === "undefined" || typeof CSSStyleSheet === "undefined") return null;

  try {
    const sheet = new CSSStyleSheet();
    document.adoptedStyleSheets = [...document.adoptedStyleSheets, sheet];
    dynamicSheet = sheet;
    return sheet;
  } catch {
    // All supported packaged WebViews expose constructable stylesheets. A
    // fixed CSS fallback keeps the menu usable on an unsupported host.
    return null;
  }
}

function selectorFor(token: string): string {
  return `.csp-positioned-overlay[data-csp-position="${token}"]`;
}

export function setCspOverlayPosition(token: string, x: number, y: number): void {
  const sheet = getDynamicSheet();
  if (!sheet) return;

  const selector = selectorFor(token);
  const existingRuleIndex = Array.from(sheet.cssRules).findIndex(
    (rule) => rule instanceof CSSStyleRule && rule.selectorText === selector,
  );
  if (existingRuleIndex >= 0) sheet.deleteRule(existingRuleIndex);

  const left = normalizedCoordinate(x);
  const top = normalizedCoordinate(y);
  sheet.insertRule(`${selector}{left:${left}px;top:${top}px;}`, sheet.cssRules.length);
}

export function clearCspOverlayPosition(token: string): void {
  if (!dynamicSheet) return;
  const selector = selectorFor(token);
  const existingRuleIndex = Array.from(dynamicSheet.cssRules).findIndex(
    (rule) => rule instanceof CSSStyleRule && rule.selectorText === selector,
  );
  if (existingRuleIndex >= 0) dynamicSheet.deleteRule(existingRuleIndex);
}
