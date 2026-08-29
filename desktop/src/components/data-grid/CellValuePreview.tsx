import { useState } from "react";
import { Copy, ExternalLink } from "lucide-react";
import { ImageCell } from "../ImageCell";
import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "../ui";
import {
  openUserConfirmedExternalHttpsUrl,
} from "../../lib/externalNavigation";
import { JsonTree } from "./json";
import { type JsonValue } from "./jsonValue";
import { classifyCellValue } from "./cellValue";
import "./CellValuePreview.css";

interface CellValuePreviewProps {
  value: unknown;
  displayValue?: string;
  detailHint?: string;
  triggerClassName?: string;
  cardClassName?: string;
  dataType?: string;
  columnName?: string;
  onCopyValue?: (value: string) => void;
}

export function CellValuePreview({
  value,
  displayValue,
  detailHint,
  triggerClassName,
  cardClassName,
  dataType,
  columnName,
  onCopyValue,
}: CellValuePreviewProps) {
  const [viewerOpen, setViewerOpen] = useState(false);
  const [hoverOpen, setHoverOpen] = useState(false);
  const presentation = classifyCellValue(value, { dataType });
  const resolvedDisplayValue = displayValue ?? presentation.displayText;
  const isJson = presentation.kind === "json";
  const parsedJson = presentation.parsedJson;

  if (presentation.kind === "null") {
    return <span className={joinClassNames("dbfox-cell-null", triggerClassName)}>NULL</span>;
  }

  if (presentation.kind === "boolean") {
    return (
      <span className={joinClassNames("dbfox-cell-boolean", presentation.displayText === "TRUE" ? "is-true" : "is-false", triggerClassName)}>
        {presentation.displayText}
      </span>
    );
  }

  if (presentation.kind === "image-url") {
    return <ImageCell url={presentation.rawText} onCopyValue={onCopyValue} />;
  }

  if (presentation.kind === "url") {
    return (
      <Dialog open={viewerOpen} onOpenChange={setViewerOpen}>
        <button
          type="button"
          data-cell-value-trigger
          className={joinClassNames("dbfox-cell-preview-link", triggerClassName)}
          title={presentation.rawText}
          aria-label={`查看链接 ${presentation.rawText}`}
          onClick={(event) => {
            event.stopPropagation();
            setViewerOpen(true);
          }}
        >
          <ExternalLink size={14} aria-hidden="true" />
          <span>{resolvedDisplayValue}</span>
        </button>
        <ValueViewerDialog
          title={columnName ? `链接 · ${columnName}` : "链接"}
          description={dataType ? `数据库类型 ${dataType}` : "HTTPS 链接"}
          presentation={presentation}
          detailHint={detailHint}
          onCopyValue={onCopyValue}
          onOpenExternal={() => void openUserConfirmedExternalHttpsUrl(presentation.rawText)}
        />
      </Dialog>
    );
  }

  if (!presentation.previewable) {
    return <span className={joinClassNames("dbfox-cell-preview-text", triggerClassName)}>{resolvedDisplayValue}</span>;
  }

  const triggerContent = isJson ? (
    <span className="dbfox-cell-preview-json-pill">{presentation.displayText}</span>
  ) : presentation.kind === "binary-placeholder" ? (
    <span className="dbfox-cell-preview-long-summary">
      <span className="dbfox-cell-preview-kind">BINARY</span>
      <span className="dbfox-cell-preview-snippet">原始字节未加载</span>
    </span>
  ) : (
    <span className="dbfox-cell-preview-long-summary" aria-label={resolvedDisplayValue}>
      <span className="dbfox-cell-preview-kind">{getTextPreviewKind(resolvedDisplayValue)}</span>
      <span className="dbfox-cell-preview-snippet">{getTextPreviewSnippet(resolvedDisplayValue)}</span>
    </span>
  );

  return (
    <Dialog open={viewerOpen} onOpenChange={setViewerOpen}>
      <HoverCard
        open={!viewerOpen && hoverOpen}
        openDelay={180}
        closeDelay={80}
        onOpenChange={(open) => {
          if (viewerOpen) return;
          setHoverOpen(open);
        }}
      >
        <HoverCardTrigger asChild>
          <button
            type="button"
            data-cell-value-trigger
            className={joinClassNames("dbfox-cell-preview-trigger", triggerClassName)}
            onClick={(event) => {
              event.stopPropagation();
              setHoverOpen(false);
              setViewerOpen(true);
            }}
          >
            {triggerContent}
          </button>
        </HoverCardTrigger>
        <HoverCardContent className={joinClassNames("dbfox-cell-preview-card", cardClassName)} side="bottom" align="start">
          <CellPreviewPanel
            value={presentation.rawText}
            isJson={isJson}
            parsedJson={parsedJson}
            detailHint="点击打开完整查看"
            binaryPlaceholder={presentation.kind === "binary-placeholder"}
            columnName={columnName}
            dataType={dataType}
          />
        </HoverCardContent>
      </HoverCard>
      <ValueViewerDialog
        title={columnName ? `${getViewerTitle(presentation.kind)} · ${columnName}` : getViewerTitle(presentation.kind)}
        description={dataType ? `数据库类型 ${dataType}` : getViewerDescription(presentation.kind)}
        presentation={presentation}
        detailHint={detailHint}
        onCopyValue={onCopyValue}
      />
    </Dialog>
  );
}

function ValueViewerDialog({
  title,
  description,
  presentation,
  detailHint,
  onCopyValue,
  onOpenExternal,
}: {
  title: string;
  description: string;
  presentation: ReturnType<typeof classifyCellValue>;
  detailHint?: string;
  onCopyValue?: (value: string) => void;
  onOpenExternal?: () => void;
}) {
  return (
    <DialogContent className="dbfox-cell-value-dialog">
      <DialogTitle>{title}</DialogTitle>
      <DialogDescription>{description}</DialogDescription>
      <CellPreviewPanel
        value={presentation.rawText}
        isJson={presentation.kind === "json"}
        parsedJson={presentation.parsedJson}
        detailHint={detailHint}
        binaryPlaceholder={presentation.kind === "binary-placeholder"}
      />
      <div className="dbfox-cell-value-actions">
        <Button
          type="button"
          size="sm"
          onClick={() => {
            if (onCopyValue) onCopyValue(presentation.copyText);
            else void navigator.clipboard.writeText(presentation.copyText);
          }}
        >
          <Copy size={14} aria-hidden="true" />
          复制值
        </Button>
        {onOpenExternal && (
          <Button type="button" size="sm" variant="outline" onClick={onOpenExternal}>
            <ExternalLink size={14} aria-hidden="true" />
            在浏览器打开
          </Button>
        )}
      </div>
    </DialogContent>
  );
}

function getViewerTitle(kind: ReturnType<typeof classifyCellValue>["kind"]) {
  if (kind === "json") return "JSON 值";
  if (kind === "binary-placeholder") return "二进制值";
  return "文本值";
}

function getViewerDescription(kind: ReturnType<typeof classifyCellValue>["kind"]) {
  if (kind === "json") return "格式化查看结构化内容";
  if (kind === "binary-placeholder") return "当前结果未包含原始二进制内容";
  return "查看完整单元格内容";
}

function CellPreviewPanel({
  value,
  isJson,
  parsedJson,
  detailHint,
  binaryPlaceholder,
  columnName,
  dataType,
}: {
  value: string;
  isJson: boolean;
  parsedJson: JsonValue | null;
  detailHint?: string;
  binaryPlaceholder: boolean;
  columnName?: string;
  dataType?: string;
}) {
  const lineCount = value.length === 0 ? 0 : value.split(/\r\n|\r|\n/).length;
  const title = binaryPlaceholder ? "二进制内容" : isJson ? "JSON 结构" : getTextPreviewTitle(value);

  return (
    <div className="dbfox-cell-preview-panel">
      <div className="dbfox-cell-preview-header">
        <div className="dbfox-cell-preview-heading">
          <span className="dbfox-cell-preview-title">{columnName ? `${title} · ${columnName}` : title}</span>
          <span className="dbfox-cell-preview-subtitle">
            {binaryPlaceholder
              ? "当前结果合同未传输原始字节"
              : isJson
                ? parsedJson ? "可展开查看字段" : "内容无法完整解析"
                : "保留原始换行和片段"}
            {dataType ? ` · ${dataType}` : ""}
          </span>
        </div>
        <div className="dbfox-cell-preview-stats" aria-label="内容统计">
          <span>{value.length} 字符</span>
          <span>{lineCount} 行</span>
        </div>
      </div>
      <div className="dbfox-cell-preview-body">
        {binaryPlaceholder ? (
          <div className="dbfox-cell-preview-binary-note">
            数据库驱动只返回了二进制占位符。DBFox 不会把占位符伪装成可下载文件。
          </div>
        ) : isJson && parsedJson ? <JsonTree data={parsedJson} /> : <StructuredTextPreview value={value} />}
      </div>
      {detailHint && <div className="dbfox-cell-preview-footer">{detailHint}</div>}
    </div>
  );
}

function StructuredTextPreview({ value }: { value: string }) {
  if (isKeyValueText(value)) {
    return (
      <div className="dbfox-cell-preview-pairs">
        {value.split(/[&;]/).map((pair, index) => {
          const eqIndex = pair.indexOf("=");
          if (eqIndex === -1) {
            return <div key={`${pair}-${index}`} className="dbfox-cell-preview-muted">{pair}</div>;
          }
          const key = pair.slice(0, eqIndex).trim();
          const pairValue = safeDecode(pair.slice(eqIndex + 1).trim());
          return (
            <div key={`${key}-${index}`} className="dbfox-cell-preview-pair">
              <span className="dbfox-cell-preview-key" title={key}>{key}</span>
              <span className="dbfox-cell-preview-value">{pairValue}</span>
            </div>
          );
        })}
      </div>
    );
  }

  if (isListText(value)) {
    return (
      <div className="dbfox-cell-preview-chips">
        {value.split(",").map((item, index) => (
          <span key={`${item}-${index}`} className="dbfox-cell-preview-chip">{item.trim()}</span>
        ))}
      </div>
    );
  }

  return <pre className="dbfox-cell-preview-pre">{value}</pre>;
}

function getTextPreviewTitle(value: string) {
  if (isKeyValueText(value)) return "键值内容";
  if (isListText(value)) return "列表内容";
  return "长文本内容";
}

function getTextPreviewKind(value: string) {
  if (isKeyValueText(value)) return "键值";
  if (isListText(value)) return "列表";
  return "文本";
}

function getTextPreviewSnippet(value: string) {
  const normalized = value.replace(/\s+/g, " ").trim();
  if (!normalized) return "空内容";
  return normalized.length > 88 ? `${normalized.slice(0, 88)}...` : normalized;
}

function isKeyValueText(value: string) {
  return value.split(/[&;]/).some((pair) => /^[^=\s][^=]*=/.test(pair.trim()));
}

function isListText(value: string) {
  return value.includes(",") && value.split(",").length > 2;
}

function safeDecode(value: string) {
  try {
    return decodeURIComponent(value.replace(/\+/g, " "));
  } catch {
    return value;
  }
}

function joinClassNames(...names: Array<string | undefined>) {
  return names.filter(Boolean).join(" ");
}
