import { Info, Sparkles, X } from "lucide-react";
import type { WorkspaceDockTab } from "../../types/workspace";
import { getStoredApiConfig } from "../../lib/llmConfig";
import "./ContextDrawer.css";

interface ContextDrawerProps {
  open: boolean;
  type: "ai-suggest" | "props";
  activeTab?: WorkspaceDockTab;
  onClose: () => void;
}

export function ContextDrawer({ open, type, activeTab, onClose }: ContextDrawerProps) {
  return (
    <section className={`context-drawer ${open ? "is-open" : "is-closed"}`}>
      <div className="context-drawer__surface">
        <div className="context-drawer__header">
          <span className="context-drawer__title">
            {type === "ai-suggest" && <><Sparkles size={13} className="context-drawer__icon context-drawer__icon--suggest" /> AI 建议</>}
            {type === "props" && <><Info size={13} className="context-drawer__icon context-drawer__icon--props" /> 对象属性</>}
          </span>
          <button type="button" className="context-drawer__close" onClick={onClose} aria-label="关闭抽屉">
            <X size={12} />
          </button>
        </div>

        <div className="context-drawer__body">
          {type === "ai-suggest" ? <AiSuggest /> : <PropsPanel activeTab={activeTab} />}
        </div>
      </div>
    </section>
  );
}

function AiSuggest() {
  return (
    <div className="context-drawer__stack">
      <span className="context-drawer__eyebrow">数据库诊断建议</span>
      <div className="context-drawer__empty">
        <Sparkles size={16} className="context-drawer__empty-icon" />
        <span>暂无诊断建议。在 SQL 控制台执行查询或与智能助手交互时，相关的性能优化建议会呈现在此处。</span>
      </div>
    </div>
  );
}

function PropsPanel({ activeTab }: { activeTab?: WorkspaceDockTab }) {
  const apiConfig = getStoredApiConfig();
  const conversationId = activeTab?.target?.type === "conversation" ? activeTab.target.id : "—";
  return (
    <InfoList
      rows={[
        ["激活大模型:", apiConfig?.modelName || "—"],
        ["会话ID:", conversationId],
      ]}
    />
  );
}

function InfoList({ rows }: { rows: string[][] }) {
  return (
    <div className="context-drawer__info-list">
      <span className="context-drawer__eyebrow">当前对象物理与 AI 属性</span>
      {rows.map(([label, value]) => {
        const isLong = value.length > 25 || label.includes("描述");
        return (
          <div key={label} className={`context-drawer__info-row ${isLong ? "context-drawer__info-row--long" : ""}`}>
            <span className="context-drawer__info-label">{label}</span>
            <span className="context-drawer__info-value">{value}</span>
          </div>
        );
      })}
    </div>
  );
}
