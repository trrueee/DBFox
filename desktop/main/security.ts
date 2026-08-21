export function developmentRendererUrl(rawUrl: string): URL {
  const url = new URL(rawUrl);
  if (
    url.protocol !== "http:"
    || url.hostname !== "127.0.0.1"
    || url.username !== ""
    || url.password !== ""
    || url.port === ""
  ) {
    throw new Error("Electron development renderer must use an explicit 127.0.0.1 HTTP origin");
  }
  return url;
}
