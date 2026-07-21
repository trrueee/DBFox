import type { ImgHTMLAttributes } from "react";

export type FoxIconVariant = "tight" | "plain" | "ai" | "ai-tight" | "app";

type FoxIconProps = Omit<ImgHTMLAttributes<HTMLImageElement>, "src" | "width" | "height" | "style"> & {
  size?: number | string;
  variant?: FoxIconVariant;
  assetBasePath?: string;
};

type FoxIconAsset = {
  basePath: string;
  file: string;
};

const assetByVariant: Record<FoxIconVariant, FoxIconAsset> = {
  tight: { basePath: "/assets/fox/svg", file: "fox-icon-tight.svg" },
  plain: { basePath: "/assets/fox/svg", file: "fox-icon.svg" },
  ai: { basePath: "/assets/fox/svg", file: "fox-icon-ai.svg" },
  "ai-tight": { basePath: "/assets/fox/svg", file: "fox-icon-ai-tight.svg" },
  app: { basePath: "/assets/fox/png", file: "fox-icon-app-transparent-512.png" },
};

export function FoxIcon({
  size = 24,
  variant = "tight",
  assetBasePath,
  alt = "DBFox fox icon",
  className,
  ...props
}: FoxIconProps) {
  const asset = assetByVariant[variant];
  const basePath = assetBasePath ?? asset.basePath;

  return (
    <img
      src={`${basePath}/${asset.file}`}
      width={size}
      height={size}
      alt={alt}
      className={["fox-icon", className].filter(Boolean).join(" ")}
      loading="eager"
      decoding="async"
      {...props}
    />
  );
}
