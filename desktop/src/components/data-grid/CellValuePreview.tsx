import { HoverCard, HoverCardContent, HoverCardTrigger } from "../ui";
import { compactJsonPreview, JsonTree, tryParseJson, type JsonValue } from "./json";
import "./CellValuePreview.css";

interface CellValuePreviewProps {
  value: unknown;
  displayValue?: string;
  detailHint?: string;
  triggerClassName?: string;
  cardClassName?: string;
}

export function cellValueToText(value: unknown) {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

export function getCellPreviewJson(value: unknown, displayValue = cellValueToText(value)): JsonValue | null {
  const parsedText = tryParseJson(displayValue);
  if (parsedText !== null) return parsedText;
  if (value === null || typeof value !== "object") return null;

  try {
    return JSON.parse(JSON.stringify(value)) as JsonValue;
  } catch {
    return null;
  }
}

export function isCellValuePreviewable(value: unknown, displayValue = cellValueToText(value)) {
  return getCellPreviewJson(value, displayValue) !== null || displayValue.length > 40 || displayValue.includes("\n");
}

export function CellValuePreview({
  value,
  displayValue = cellValueToText(value),
  detailHint,
  triggerClassName,
  cardClassName,
}: CellValuePreviewProps) {
  const parsedJson = getCellPreviewJson(value, displayValue);
  const isJson = parsedJson !== null;
  const previewable = isJson || displayValue.length > 40 || displayValue.includes("\n");

  if (!previewable) {
    return <span className={joinClassNames("dbfox-cell-preview-text", triggerClassName)}>{displayValue}</span>;
  }

  const triggerContent = isJson && parsedJson ? (
    <span className="dbfox-cell-preview-json-pill">JSON · {compactJsonPreview(parsedJson)}</span>
  ) : (
    <span className="dbfox-cell-preview-long-summary" aria-label={displayValue}>
      <span className="dbfox-cell-preview-kind">{getTextPreviewKind(displayValue)}</span>
      <span className="dbfox-cell-preview-snippet">{getTextPreviewSnippet(displayValue)}</span>
    </span>
  );

  return (
    <HoverCard openDelay={180} closeDelay={80}>
      <HoverCardTrigger asChild>
        <span className={joinClassNames("dbfox-cell-preview-trigger", triggerClassName)}>{triggerContent}</span>
      </HoverCardTrigger>
      <HoverCardContent className={joinClassNames("dbfox-cell-preview-card", cardClassName)} side="bottom" align="start">
        <CellPreviewPanel value={displayValue} isJson={isJson} parsedJson={parsedJson} detailHint={detailHint} />
      </HoverCardContent>
    </HoverCard>
  );
}

function CellPreviewPanel({
  value,
  isJson,
  parsedJson,
  detailHint,
}: {
  value: string;
  isJson: boolean;
  parsedJson: JsonValue | null;
  detailHint?: string;
}) {
  const lineCount = value.length === 0 ? 0 : value.split(/\r\n|\r|\n/).length;
  const title = isJson ? "JSON 结构" : getTextPreviewTitle(value);

  return (
    <div className="dbfox-cell-preview-panel">
      <div className="dbfox-cell-preview-header">
        <div className="dbfox-cell-preview-heading">
          <span className="dbfox-cell-preview-title">{title}</span>
          <span className="dbfox-cell-preview-subtitle">{isJson ? "可展开查看字段" : "保留原始换行和片段"}</span>
        </div>
        <div className="dbfox-cell-preview-stats" aria-label="内容统计">
          <span>{value.length} 字符</span>
          <span>{lineCount} 行</span>
        </div>
      </div>
      <div className="dbfox-cell-preview-body">
        {isJson && parsedJson ? <JsonTree data={parsedJson} /> : <StructuredTextPreview value={value} />}
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
