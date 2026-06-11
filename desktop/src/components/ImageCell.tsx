import { useRef, useState } from "react";
import { createPortal } from "react-dom";
import { ExternalLink, ImageOff, X } from "lucide-react";

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

interface PopoverPos {
  left: number;
  top: number;
}

export function ImageCell({ url }: { url: string }) {
  const anchorRef = useRef<HTMLSpanElement>(null);
  const [popoverPos, setPopoverPos] = useState<PopoverPos | null>(null);
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

  const showPopover = () => {
    const rect = anchorRef.current?.getBoundingClientRect();
    if (!rect) return;
    const previewSize = 260;
    const margin = 12;
    let left = rect.left;
    let top = rect.bottom + 6;
    if (left + previewSize + margin > window.innerWidth) left = window.innerWidth - previewSize - margin;
    if (top + previewSize + margin > window.innerHeight) top = rect.top - previewSize - 6;
    setPopoverPos({ left: Math.max(margin, left), top: Math.max(margin, top) });
  };

  return (
    <>
      <span
        ref={anchorRef}
        className="hifi-img-cell"
        title={url}
        onMouseEnter={showPopover}
        onMouseLeave={() => setPopoverPos(null)}
        onClick={(event) => {
          event.stopPropagation();
          setPopoverPos(null);
          setLightboxOpen(true);
        }}
      >
        <img className="hifi-img-thumb" src={url} loading="lazy" alt="" onError={() => setBroken(true)} />
        <span className="hifi-img-url">{url}</span>
      </span>

      {popoverPos && !lightboxOpen &&
        createPortal(
          <div className="hifi-img-popover" style={{ left: popoverPos.left, top: popoverPos.top }}>
            <img src={url} alt="" />
            <div className="hifi-img-popover-hint">点击查看大图</div>
          </div>,
          document.body,
        )}

      {lightboxOpen &&
        createPortal(
          <div className="hifi-img-lightbox" onClick={() => setLightboxOpen(false)}>
            <button className="hifi-img-lightbox-close" onClick={() => setLightboxOpen(false)} title="关闭">
              <X size={16} />
            </button>
            <img src={url} alt="" onClick={(event) => event.stopPropagation()} />
            <div className="hifi-img-lightbox-bar" onClick={(event) => event.stopPropagation()}>
              <span className="hifi-img-lightbox-url" title={url}>{url}</span>
              <button onClick={() => window.open(url, "_blank", "noopener")} title="在浏览器打开">
                <ExternalLink size={12} /> 打开原图
              </button>
            </div>
          </div>,
          document.body,
        )}
    </>
  );
}
