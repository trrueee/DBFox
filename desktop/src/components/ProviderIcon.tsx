import { PROVIDER_ICON_PATHS } from "./brand/providerPaths";

const MONOGRAMS: Readonly<Record<string, string>> = Object.freeze({
  openai: "OA",
  zhipu: "ZP",
  xai: "XA",
  siliconflow: "SF",
  hunyuan: "HY",
});

/**
 * Brand glyph for an LLM provider. Renders the bundled simple-icons path when
 * one exists and a neutral monogram tile otherwise, so unknown or
 * trademark-withheld brands still read as provider chips inside form controls.
 * Pure SVG — the desktop CSP forbids inline style attributes.
 */
export function ProviderIcon({
  provider,
  size = 16,
}: {
  provider?: string | null;
  size?: number;
}) {
  const id = (provider ?? "").toLowerCase();
  const path = PROVIDER_ICON_PATHS[id];
  if (path) {
    return (
      <svg
        viewBox="0 0 24 24"
        width={size}
        height={size}
        fill="currentColor"
        aria-hidden="true"
        focusable="false"
      >
        <path d={path} />
      </svg>
    );
  }
  const monogram = MONOGRAMS[id] ?? (id.replace(/[^a-z0-9]/g, "").slice(0, 2).toUpperCase() || "·");
  return (
    <svg
      viewBox="0 0 16 16"
      width={size}
      height={size}
      aria-hidden="true"
      focusable="false"
    >
      <rect
        x="0.5"
        y="0.5"
        width="15"
        height="15"
        rx="3.5"
        fill="none"
        stroke="currentColor"
        strokeOpacity="0.35"
      />
      <text
        x="8"
        y="8.5"
        textAnchor="middle"
        dominantBaseline="central"
        fontSize="8"
        fontWeight="600"
        fill="currentColor"
      >
        {monogram}
      </text>
    </svg>
  );
}
