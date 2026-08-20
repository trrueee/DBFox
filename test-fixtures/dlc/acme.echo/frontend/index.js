const sdk = window.__DBFOX_EXTENSION_HOST__;

function react() {
  if (!sdk?.React) {
    throw new Error("DBFox Frontend Extension Host SDK is unavailable");
  }
  return sdk.React;
}

function parseEchoPayload(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Acme Echo artifact payload must be an object");
  }
  if (typeof value.message !== "string" || value.message.trim() === "") {
    throw new Error("Acme Echo artifact payload requires message");
  }
  return { message: value.message };
}

export function register(host) {
  host.dockViews.register({
    viewType: "acme.echo.dock",
    icon: () => react().createElement("span", { "aria-hidden": true }, "E"),
    resolveTitle: () => "Acme Echo",
    isVisible: () => true,
    render: () => react().createElement("section", null, "Acme Echo is active"),
  });

  host.artifactRenderers.register({
    type: "acme.echo.message",
    supportedSchemaVersions: [1],
    parsePayload: parseEchoPayload,
    render: (artifact) => {
      const payload = parseEchoPayload(artifact.payload);
      return react().createElement("p", null, payload.message);
    },
  });
}
