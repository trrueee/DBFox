import { Check, Copy, X } from "lucide-react";
import { useMemo, useState } from "react";
import { JsonTree } from "./json";
import { tryParseJson } from "./jsonValue";
import type { DataGridInspectState } from "./types";

interface DataGridInspectorProps {
  inspect: DataGridInspectState | null;
  onClose: () => void;
  onCopy: (value: string) => Promise<void>;
}

export function DataGridInspector({ inspect, onClose, onCopy }: DataGridInspectorProps) {
  const [mode, setMode] = useState<"tree" | "raw">("tree");
  const [copied, setCopied] = useState(false);

  const parsed = useMemo(() => inspect?.isJson ? tryParseJson(inspect.value) : null, [inspect]);

  if (!inspect) return null;

  const handleCopy = async () => {
    await onCopy(inspect.value);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="data-grid-inspector-backdrop" onClick={onClose}>
      <div className="data-grid-inspector" onClick={(event) => event.stopPropagation()}>
        <header className="data-grid-inspector-header">
          <div className="data-grid-inspector-title">{inspect.column}</div>
          <div className="flex items-center gap-2">
            {inspect.isJson && (
              <div className="data-grid-button">
                <button type="button" className="border-0 bg-transparent cursor-pointer font-bold text-inherit" onClick={() => setMode("tree")}>Tree</button>
                <span className="opacity-40">/</span>
                <button type="button" className="border-0 bg-transparent cursor-pointer font-bold text-inherit" onClick={() => setMode("raw")}>Raw</button>
              </div>
            )}
            <button className="data-grid-button" type="button" onClick={handleCopy}>
              {copied ? <Check size={13} /> : <Copy size={13} />}
              {copied ? "已复制" : "复制"}
            </button>
            <button className="data-grid-button" type="button" onClick={onClose}>
              <X size={13} />
            </button>
          </div>
        </header>
        <div className="data-grid-inspector-body">
          {inspect.isJson && parsed && mode === "tree" ? (
            <JsonTree data={parsed} />
          ) : (
            <pre className="data-grid-inspector-pre">{inspect.value}</pre>
          )}
        </div>
      </div>
    </div>
  );
}
