import { useState, type KeyboardEvent } from "react";
import {
  Copy,
  Download,
  ExternalLink,
  Image,
  ImageOff,
  LoaderCircle,
  Maximize,
  Minus,
  Plus,
  Scan,
} from "lucide-react";
import {
  canSaveExternalImage,
  canOpenExternalHttpsUrl,
  openUserConfirmedExternalHttpsUrl,
  saveUserConfirmedExternalImage,
} from "../lib/externalNavigation";
import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DialogTrigger,
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "./ui";
import "./ImageCell.css";

const IMAGE_ZOOM_LEVELS = [100, 125, 150, 200] as const;
type ImageZoomLevel = (typeof IMAGE_ZOOM_LEVELS)[number];
type ImageViewMode = "fit" | "actual";

export function ImageCell({ url, onCopyValue }: { url: string; onCopyValue?: (value: string) => void }) {
  return <ImageCellContent key={url} url={url} onCopyValue={onCopyValue} />;
}

function ImageCellContent({ url, onCopyValue }: { url: string; onCopyValue?: (value: string) => void }) {
  const [previewOpen, setPreviewOpen] = useState(false);
  const [loadState, setLoadState] = useState<"loading" | "ready" | "failed">("loading");
  const [hoverOpen, setHoverOpen] = useState(false);
  const [hoverLoadState, setHoverLoadState] = useState<"loading" | "ready" | "failed">("loading");
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved" | "failed">("idle");
  const [viewMode, setViewMode] = useState<ImageViewMode>("fit");
  const [zoomLevel, setZoomLevel] = useState<ImageZoomLevel>(100);
  const [imageDimensions, setImageDimensions] = useState<{ width: number; height: number } | null>(null);
  const canOpenOriginalExternally = canOpenExternalHttpsUrl(url);
  const canSaveCopy = canSaveExternalImage(url);

  const changeZoom = (direction: -1 | 1) => {
    setZoomLevel((current) => {
      const currentIndex = IMAGE_ZOOM_LEVELS.indexOf(current);
      const nextIndex = Math.min(
        IMAGE_ZOOM_LEVELS.length - 1,
        Math.max(0, currentIndex + direction),
      );
      return IMAGE_ZOOM_LEVELS[nextIndex];
    });
  };

  const resetView = () => {
    setViewMode("fit");
    setZoomLevel(100);
  };

  const showActualSize = () => {
    setViewMode("actual");
    setZoomLevel(100);
  };

  const handleCanvasKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "+" || event.key === "=") {
      event.preventDefault();
      changeZoom(1);
    } else if (event.key === "-") {
      event.preventDefault();
      changeZoom(-1);
    } else if (event.key === "0") {
      event.preventDefault();
      resetView();
    } else if (event.key === "1") {
      event.preventDefault();
      showActualSize();
    }
  };

  return (
    <Dialog
      open={previewOpen}
      onOpenChange={(open) => {
        setPreviewOpen(open);
        if (open) {
          setLoadState("loading");
          setSaveState("idle");
          setImageDimensions(null);
          resetView();
        }
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
          <DialogTrigger asChild>
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
              }}
            >
              <Image className="hifi-img-icon" size={14} aria-hidden="true" />
              <span className="hifi-img-url">{url}</span>
            </button>
          </DialogTrigger>
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
              alt="数据单元格中的图片悬浮预览"
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
        <div className="hifi-img-view-toolbar" role="toolbar" aria-label="图片查看控制">
          <div className="hifi-img-view-toolbar__group hifi-img-view-toolbar__zoom" role="group" aria-label="缩放">
            <Button
              type="button"
              size="icon-sm"
              variant="ghost"
              aria-label="缩小图片"
              title="缩小（-）"
              disabled={loadState !== "ready" || zoomLevel === IMAGE_ZOOM_LEVELS[0]}
              onClick={() => changeZoom(-1)}
            >
              <Minus size={14} aria-hidden="true" />
            </Button>
            <span className="hifi-img-view-toolbar__scale" role="status" aria-live="polite">
              {viewMode === "fit" ? `适应 · ${zoomLevel}%` : `实际大小 · ${zoomLevel}%`}
            </span>
            <Button
              type="button"
              size="icon-sm"
              variant="ghost"
              aria-label="放大图片"
              title="放大（+）"
              disabled={loadState !== "ready" || zoomLevel === IMAGE_ZOOM_LEVELS.at(-1)}
              onClick={() => changeZoom(1)}
            >
              <Plus size={14} aria-hidden="true" />
            </Button>
          </div>
          <div className="hifi-img-view-toolbar__separator" role="separator" aria-orientation="vertical" />
          <div className="hifi-img-view-toolbar__group" role="group" aria-label="显示方式">
            <Button
              type="button"
              size="sm"
              variant={viewMode === "fit" && zoomLevel === 100 ? "secondary" : "ghost"}
              disabled={loadState !== "ready"}
              aria-pressed={viewMode === "fit" && zoomLevel === 100}
              onClick={resetView}
            >
              <Scan size={14} aria-hidden="true" />
              适应窗口
            </Button>
            <Button
              type="button"
              size="sm"
              variant={viewMode === "actual" && zoomLevel === 100 ? "secondary" : "ghost"}
              disabled={loadState !== "ready"}
              aria-pressed={viewMode === "actual" && zoomLevel === 100}
              onClick={showActualSize}
            >
              <Maximize size={14} aria-hidden="true" />
              实际大小
            </Button>
          </div>
          <span className="hifi-img-view-toolbar__hint">方向键或滚动条移动 · 0 复位 · 1 实际大小</span>
        </div>
        <div
          className="hifi-img-lightbox-stage"
          data-state={loadState}
          tabIndex={loadState === "ready" ? 0 : -1}
          aria-label="图片画布；使用加号和减号缩放，方向键移动，0 适应窗口，1 显示实际大小"
          onKeyDown={handleCanvasKeyDown}
        >
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
          <div className="hifi-img-lightbox-canvas" data-view-mode={viewMode} data-zoom={zoomLevel}>
            <img
              className="hifi-img-lightbox-image"
              data-view-mode={viewMode}
              data-zoom={zoomLevel}
              src={url}
              alt="数据单元格中的图片预览"
              draggable={false}
              referrerPolicy="no-referrer"
              onLoad={(event) => {
                setImageDimensions({
                  width: event.currentTarget.naturalWidth,
                  height: event.currentTarget.naturalHeight,
                });
                setLoadState("ready");
              }}
              onError={() => setLoadState("failed")}
            />
          </div>
        </div>
        <div className="hifi-img-lightbox-bar">
          <div className="hifi-img-lightbox-meta">
            <span className="hifi-img-lightbox-url" title={url}>{url}</span>
            {imageDimensions ? (
              <span className="hifi-img-lightbox-dimensions">
                {imageDimensions.width} × {imageDimensions.height} px
              </span>
            ) : null}
          </div>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => {
              if (onCopyValue) onCopyValue(url);
              else void navigator.clipboard.writeText(url);
            }}
          >
            <Copy size={14} aria-hidden="true" />
            复制链接
          </Button>
          {canSaveCopy && (
            <Button
              type="button"
              size="sm"
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
              {saveState === "saving" ? <LoaderCircle className="hifi-img-loading-icon" size={14} aria-hidden="true" /> : <Download size={14} aria-hidden="true" />}
              {saveState === "saving" ? "正在保存" : saveState === "saved" ? "已保存" : "保存副本"}
            </Button>
          )}
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => void openUserConfirmedExternalHttpsUrl(url)}
          >
            <ExternalLink size={14} aria-hidden="true" />
            在浏览器打开
          </Button>
        </div>
        {saveState === "failed" && <div className="hifi-img-save-error" role="alert">图片保存失败，请检查地址、网络或文件权限</div>}
      </DialogContent>
    </Dialog>
  );
}
