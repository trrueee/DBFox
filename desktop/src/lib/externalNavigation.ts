const EXTERNAL_WINDOW_FEATURES = "noopener,noreferrer";

/**
 * Parse an external URL only when it is safe to hand to the system browser.
 *
 * DBFox renders data controlled by connected databases, so links must never
 * inherit browser privileges merely because they appear in a result cell.
 * Only absolute HTTPS URLs without user-info are eligible for a direct user
 * gesture to open.
 */
export function parseExternalHttpsUrl(rawUrl: string): URL | null {
  if (typeof rawUrl !== "string" || rawUrl.length === 0 || rawUrl !== rawUrl.trim()) {
    return null;
  }

  try {
    const url = new URL(rawUrl);
    if (
      url.protocol !== "https:"
      || !url.hostname
      || url.username.length > 0
      || url.password.length > 0
    ) {
      return null;
    }
    return url;
  } catch {
    return null;
  }
}

export function canOpenExternalHttpsUrl(rawUrl: string): boolean {
  return parseExternalHttpsUrl(rawUrl) !== null;
}

/**
 * Open a URL after an explicit user click has already confirmed the action.
 *
 * Call this only from a direct UI event handler.  It intentionally has no
 * Tauri shell/opener fallback: browser navigation remains constrained by the
 * WebView and is always opened without an opener or referrer relationship.
 */
export function openUserConfirmedExternalHttpsUrl(rawUrl: string): boolean {
  const url = parseExternalHttpsUrl(rawUrl);
  if (!url || typeof window === "undefined") {
    return false;
  }

  try {
    const openedWindow = window.open(url.href, "_blank", EXTERNAL_WINDOW_FEATURES);
    if (openedWindow) {
      // Keep the isolation guarantee even in WebViews that do not fully honor
      // the feature string.
      try {
        openedWindow.opener = null;
      } catch {
        // The browser-level noopener feature remains the primary guarantee.
      }
    }
    return openedWindow !== null;
  } catch {
    return false;
  }
}
