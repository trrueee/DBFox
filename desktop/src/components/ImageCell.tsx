import { useState } from "react";
import { ExternalLink, ImageOff } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "./ui";
import "./ImageCell.css";

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
    // Aliyun OSS / cloud CDN style processed images without extension
    const query = url.search.toLowerCase();
    return query.includes("x-oss-process=image") || query.includes("imageview2") || query.includes("imagemogr2");
  } catch {
    return false;
  }
}

export function ImageCell({ url }: { url: string }) {
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const [broken, setBroken] = useState(false);

  if (broken) {
    return (
      <span className="hifi-img-cell" title={url}>
        <span className="hifi-img-thumb hifi-img-thumb-broken"><ImageOff size={11} /></span>
        <span className="hifi-img-url">{url}</span>
      </span>
    );
  }

  return (
    <Dialog open={lightboxOpen} onOpenChange={setLightboxOpen}>
      <HoverCard openDelay={160} closeDelay={80}>
        <HoverCardTrigger asChild>
          <button
            type="button"
            className="hifi-img-cell"
            title={url}
            aria-label={`预览图片 ${url}`}
            onClick={(event) => {
              event.stopPropagation();
              setLightboxOpen(true);
            }}
          >
            <img className="hifi-img-thumb" src={url} loading="lazy" alt="" onError={() => setBroken(true)} />
            <span className="hifi-img-url">{url}</span>
          </button>
        </HoverCardTrigger>
        <HoverCardContent className="hifi-img-hover-card" side="bottom" align="start">
          <img src={url} alt="" />
          <div className="hifi-img-hover-card-hint">点击查看大图</div>
        </HoverCardContent>
      </HoverCard>

      <DialogContent className="hifi-img-lightbox">
        <DialogTitle className="hifi-img-lightbox-title">图片预览</DialogTitle>
        <DialogDescription className="hifi-img-lightbox-description">{url}</DialogDescription>
        <img className="hifi-img-lightbox-image" src={url} alt="" />
        <div className="hifi-img-lightbox-bar">
          <span className="hifi-img-lightbox-url" title={url}>{url}</span>
          <button type="button" onClick={() => window.open(url, "_blank", "noopener")} title="在浏览器打开">
            <ExternalLink size={12} /> 打开原图
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
