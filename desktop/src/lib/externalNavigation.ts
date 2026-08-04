import { invoke, isTauri } from "@tauri-apps/api/core";

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
 * Open a URL in the operating system's default browser after a direct user
 * gesture. The Rust host repeats the policy validation before delegating to
 * Tauri's official opener plugin.
 */
export async function openUserConfirmedExternalHttpsUrl(rawUrl: string): Promise<boolean> {
  const url = parseExternalHttpsUrl(rawUrl);
  if (!url || !isTauri()) {
    return false;
  }

  try {
    await invoke("open_external_https_url", { url: url.href });
    return true;
  } catch {
    return false;
  }
}
