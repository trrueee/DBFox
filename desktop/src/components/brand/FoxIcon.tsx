import type { ImgHTMLAttributes } from "react";

export type FoxIconVariant = "ai-tight" | "app";

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
  "ai-tight": { basePath: "/assets/fox/png", file: "fox-icon-ai-tight-256.png" },
  app: { basePath: "/assets/fox/png", file: "fox-icon-app-transparent-512.png" },
};

export function FoxIcon({
  size = 24,
  variant = "app",
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
