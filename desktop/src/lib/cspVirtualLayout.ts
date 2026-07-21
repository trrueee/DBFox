/**
 * Publish virtual-list geometry through a constructable stylesheet.
 *
 * DBFox rejects style attributes (`style-src-attr 'none'`). Virtualizers still
 * need per-frame pixel geometry, so the approved boundary is a CSSOM sheet
 * whose selectors and numeric values are fully normalized here.
 */
const MAX_LAYOUT_SIZE = 100_000_000;

let virtualLayoutSheet: CSSStyleSheet | null = null;

export interface VirtualLayoutItem {
  index: number;
  start: number;
}

function normalizedToken(value: string): string {
  const token = value.replace(/[^a-zA-Z0-9_-]/g, "").slice(0, 64);
  if (!token) throw new Error("Virtual layout token is empty");
  return token;
}

function normalizedPixel(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.min(MAX_LAYOUT_SIZE, Math.max(0, Math.round(value)));
}

function normalizedIndex(value: number): number {
  if (!Number.isSafeInteger(value) || value < 0) throw new Error("Virtual row index is invalid");
  return value;
}

function getVirtualLayoutSheet(): CSSStyleSheet | null {
  if (virtualLayoutSheet) return virtualLayoutSheet;
  if (typeof document === "undefined" || typeof CSSStyleSheet === "undefined") return null;

  try {
    const sheet = new CSSStyleSheet();
    document.adoptedStyleSheets = [...document.adoptedStyleSheets, sheet];
    virtualLayoutSheet = sheet;
    return sheet;
  } catch {
    return null;
  }
}

function layoutMarker(token: string): string {
  return `[data-virtual-layout="${token}"]`;
}

function deleteLayoutRules(sheet: CSSStyleSheet, token: string): void {
  const marker = layoutMarker(token);
  for (let index = sheet.cssRules.length - 1; index >= 0; index -= 1) {
    const rule = sheet.cssRules[index];
    if (rule instanceof CSSStyleRule && rule.selectorText.includes(marker)) {
      sheet.deleteRule(index);
    }
  }
}

export function setCspVirtualLayout(
  rawToken: string,
  totalSize: number,
  items: readonly VirtualLayoutItem[],
): void {
  const sheet = getVirtualLayoutSheet();
  if (!sheet) return;

  const token = normalizedToken(rawToken);
  const marker = layoutMarker(token);
  deleteLayoutRules(sheet, token);
  sheet.insertRule(
    `.conv-message-column${marker}{height:${normalizedPixel(totalSize)}px;}`,
    sheet.cssRules.length,
  );
  for (const item of items) {
    const index = normalizedIndex(item.index);
    const start = normalizedPixel(item.start);
    sheet.insertRule(
      `.conv-message-virtual-row${marker}[data-index="${index}"]{transform:translateY(${start}px);}`,
      sheet.cssRules.length,
    );
  }
}

export function clearCspVirtualLayout(rawToken: string): void {
  if (!virtualLayoutSheet) return;
  deleteLayoutRules(virtualLayoutSheet, normalizedToken(rawToken));
}
