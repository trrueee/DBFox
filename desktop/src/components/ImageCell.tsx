import { ExternalLink } from "lucide-react";
import {
  canOpenExternalHttpsUrl,
  openUserConfirmedExternalHttpsUrl,
} from "../lib/externalNavigation";
import "./ImageCell.css";

export function ImageCell({ url }: { url: string }) {
  const canOpenOriginalExternally = canOpenExternalHttpsUrl(url);

  return (
    <button
      type="button"
      className="hifi-img-cell"
      disabled={!canOpenOriginalExternally}
      title={canOpenOriginalExternally ? "在系统浏览器打开图片" : "仅允许打开 HTTPS 图片链接"}
      aria-label={`在系统浏览器打开图片 ${url}`}
      onClick={(event) => {
        event.stopPropagation();
        void openUserConfirmedExternalHttpsUrl(url);
      }}
    >
      <ExternalLink className="hifi-img-icon" size={14} aria-hidden="true" />
      <span className="hifi-img-url">{url}</span>
    </button>
  );
}
