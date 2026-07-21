const IMAGE_EXTENSIONS = [".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp", ".ico", ".avif"];

/** Detects http(s) URLs that point to an image (by extension or OSS image-process params). */
export function isImageUrl(value: string | null | undefined): value is string {
  if (!value) return false;
  const text = value.trim();
  if (!/^https?:\/\//i.test(text) || /\s/.test(text)) return false;
  try {
    const url = new URL(text);
    const pathname = url.pathname.toLowerCase();
    if (IMAGE_EXTENSIONS.some((ext) => pathname.endsWith(ext))) return true;
    const query = url.search.toLowerCase();
    return query.includes("x-oss-process=image") || query.includes("imageview2") || query.includes("imagemogr2");
  } catch {
    return false;
  }
}
