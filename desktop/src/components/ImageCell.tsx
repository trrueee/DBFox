import { useState } from "react";
import { Copy, Download, ExternalLink, Image, ImageOff, LoaderCircle } from "lucide-react";
import {
  canSaveExternalImage,
  canOpenExternalHttpsUrl,
  openUserConfirmedExternalHttpsUrl,
  saveUserConfirmedExternalImage,
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

export function ImageCell({ url, onCopyValue }: { url: string; onCopyValue?: (value: string) => void }) {
  const [previewOpen, setPreviewOpen] = useState(false);
  const [loadState, setLoadState] = useState<"loading" | "ready" | "failed">("loading");
  const [hoverOpen, setHoverOpen] = useState(false);
  const [hoverLoadState, setHoverLoadState] = useState<"loading" | "ready" | "failed">("loading");
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved" | "failed">("idle");
  const canOpenOriginalExternally = canOpenExternalHttpsUrl(url);
  const canSaveCopy = canSaveExternalImage(url);

  return (
    <Dialog
      open={previewOpen}
      onOpenChange={(open) => {
        setPreviewOpen(open);
        if (open) setLoadState("loading");
      }}
    >
      <HoverCard
        open={canOpenOriginalExternally && hoverOpen && !previewOpen}
        openDelay={400}
        closeDelay={80}
        onOpenChange={(open) => {
          if (previewOpen) return;
          setHoverOpen(open);
          if (open) setHoverLoadState("loading");
        }}
      >
        <HoverCardTrigger asChild>
          <button
            type="button"
            data-cell-value-trigger
            className="hifi-img-cell"
            disabled={!canOpenOriginalExternally}
            title={canOpenOriginalExternally ? "悬浮预览，点击查看大图" : "仅允许预览 HTTPS 图片链接"}
            aria-label={`预览图片 ${url}`}
            onClick={(event) => {
              event.stopPropagation();
              setHoverOpen(false);
              setPreviewOpen(true);
            }}
          >
            <Image className="hifi-img-icon" size={14} aria-hidden="true" />
            <span className="hifi-img-url">{url}</span>
          </button>
        </HoverCardTrigger>
        <HoverCardContent className="hifi-img-hover-card" side="bottom" align="start" sideOffset={6}>
          <div className="hifi-img-hover-stage" data-state={hoverLoadState}>
            {hoverLoadState === "loading" && (
              <div className="hifi-img-hover-status" role="status">
                <LoaderCircle className="hifi-img-loading-icon" size={16} aria-hidden="true" />
                正在加载预览
              </div>
            )}
            {hoverLoadState === "failed" && (
              <div className="hifi-img-hover-status is-error" role="alert">
                <ImageOff size={16} aria-hidden="true" />
                无法预览图片
              </div>
            )}
            <img
              className="hifi-img-hover-image"
              src={url}
              alt="数据库单元格中的图片悬浮预览"
              referrerPolicy="no-referrer"
              onLoad={() => setHoverLoadState("ready")}
              onError={() => setHoverLoadState("failed")}
            />
          </div>
          <div className="hifi-img-hover-hint">点击查看大图</div>
        </HoverCardContent>
      </HoverCard>

      <DialogContent className="hifi-img-lightbox">
        <DialogTitle className="hifi-img-lightbox-title">图片预览</DialogTitle>
        <DialogDescription className="hifi-img-lightbox-description" title={url}>{url}</DialogDescription>
        <div className="hifi-img-lightbox-stage" data-state={loadState}>
          {loadState === "loading" && (
            <div className="hifi-img-lightbox-status" role="status">
              <LoaderCircle className="hifi-img-loading-icon" size={20} aria-hidden="true" />
              正在加载图片
            </div>
          )}
          {loadState === "failed" && (
            <div className="hifi-img-lightbox-status is-error" role="alert">
              <ImageOff size={20} aria-hidden="true" />
              图片无法预览，可尝试在系统浏览器中打开
            </div>
          )}
          <img
            className="hifi-img-lightbox-image"
            src={url}
            alt="数据库单元格中的图片预览"
            referrerPolicy="no-referrer"
            onLoad={() => setLoadState("ready")}
            onError={() => setLoadState("failed")}
          />
        </div>
        <div className="hifi-img-lightbox-bar">
          <span className="hifi-img-lightbox-url" title={url}>{url}</span>
          <button
            type="button"
            onClick={() => {
              if (onCopyValue) onCopyValue(url);
              else void navigator.clipboard.writeText(url);
            }}
          >
            <Copy size={12} aria-hidden="true" />
            复制链接
          </button>
          {canSaveCopy && (
            <button
              type="button"
              disabled={saveState === "saving"}
              onClick={async () => {
                setSaveState("saving");
                try {
                  const result = await saveUserConfirmedExternalImage(url);
                  setSaveState(result.status === "saved" ? "saved" : "idle");
                } catch {
                  setSaveState("failed");
                }
              }}
            >
              {saveState === "saving" ? <LoaderCircle className="hifi-img-loading-icon" size={12} aria-hidden="true" /> : <Download size={12} aria-hidden="true" />}
              {saveState === "saving" ? "正在保存" : saveState === "saved" ? "已保存" : "保存副本"}
            </button>
          )}
          <button
            type="button"
            onClick={() => void openUserConfirmedExternalHttpsUrl(url)}
          >
            <ExternalLink size={12} aria-hidden="true" />
            在浏览器打开
          </button>
        </div>
        {saveState === "failed" && <div className="hifi-img-save-error" role="alert">图片保存失败，请检查地址、网络或文件权限</div>}
      </DialogContent>
    </Dialog>
  );
}
