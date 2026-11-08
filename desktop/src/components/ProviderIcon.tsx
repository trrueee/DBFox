import { PlugsConnectedIcon } from "@/components/icons";
import { PROVIDER_ICONS } from "./brand/providerPaths";

/**
 * Recognizable, offline provider marks. Custom providers use the shared connection glyph.
 */
export function ProviderIcon({
  provider,
  size = 20,
}: {
  provider?: string | null;
  size?: number;
}) {
  const id = (provider ?? "").toLowerCase();
  const icon = PROVIDER_ICONS[id];
  if (icon) {
    return (
      <svg
        viewBox="0 0 24 24"
        width={size}
        height={size}
        fill="currentColor"
        aria-hidden="true"
        focusable="false"
      >
        <path d={icon.path} fillRule={icon.fillRule} />
      </svg>
    );
  }
  return <PlugsConnectedIcon size={size} weight="regular" aria-hidden="true" />;
}
