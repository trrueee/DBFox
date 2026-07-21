import { useState } from "react";
import { ExternalLink, ImageOff } from "lucide-react";
import {
  canOpenExternalHttpsUrl,
  openUserConfirmedExternalHttpsUrl,
} from "../lib/externalNavigation";
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

export function ImageCell({ url }: { url: string }) {
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const [broken, setBroken] = useState(false);
  const canOpenOriginalExternally = canOpenExternalHttpsUrl(url);

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
          <button
            type="button"
            disabled={!canOpenOriginalExternally}
            onClick={() => openUserConfirmedExternalHttpsUrl(url)}
            title={canOpenOriginalExternally ? "在浏览器打开" : "仅允许打开 HTTPS 图片链接"}
          >
            <ExternalLink size={12} /> 打开原图
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
