import * as React from "react";

export type FoxIconVariant = "tight" | "plain" | "ai" | "ai-tight" | "app";

type FoxIconProps = Omit<React.ImgHTMLAttributes<HTMLImageElement>, "src" | "width" | "height"> & {
  size?: number | string;
  variant?: FoxIconVariant;
  assetBasePath?: string;
};

const fileByVariant: Record<FoxIconVariant, string> = {
  tight: "fox-icon-tight.svg",
  plain: "fox-icon.svg",
  ai: "fox-icon-ai.svg",
  "ai-tight": "fox-icon-ai-tight.svg",
  app: "fox-icon-app.svg",
};

export function FoxIcon({
  size = 24,
  variant = "tight",
  assetBasePath = "/assets/fox/svg",
  alt = "Arctic Fox icon",
  style,
  ...props
}: FoxIconProps) {
  return (
    <img
      src={`${assetBasePath}/${fileByVariant[variant]}`}
      width={size}
      height={size}
      alt={alt}
      loading="eager"
      decoding="async"
      style={{ display: "inline-block", verticalAlign: "middle", ...style }}
      {...props}
    />
  );
}
