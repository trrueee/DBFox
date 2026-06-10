import { useState } from "react";
import { AlertTriangle, DatabaseZap, Loader2, X } from "lucide-react";
import { api } from "../../lib/api";
import type { DataSource, SchemaTable } from "../../lib/api";

interface TestDataGeneratorDialogProps {
  datasource: DataSource;
  table: SchemaTable | null;
  open: boolean;
  onClose: () => void;
  onGenerated: () => void;
}

export function TestDataGeneratorDialog({ datasource, table, open, onClose, onGenerated }: TestDataGeneratorDialogProps) {
  const [rowCount, setRowCount] = useState(10);
  const [language, setLanguage] = useState<"zh" | "en">("zh");
  const [confirmText, setConfirmText] = useState("");
  const [confirmToken, setConfirmToken] = useState<string | null>(null);
  const [expectedConfirmText, setExpectedConfirmText] = useState("");
  const [impactSummary, setImpactSummary] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (!open || !table) return null;

  const resetAndClose = () => {
    setConfirmText("");
    setConfirmToken(null);
    setExpectedConfirmText("");
    setImpactSummary("");
    setMessage(null);
    setError(null);
    onClose();
  };

  const submit = async () => {
    setSubmitting(true);
    setError(null);
    setMessage(null);
    try {
      const result = await api.generateTestData(
        {
          datasource_id: datasource.id,
          table_name: table.table_name,
          row_count: rowCount,
          language,
        },
        confirmToken ? { token: confirmToken, text: confirmText } : undefined,
      );

      if ("requires_confirmation" in result && result.requires_confirmation) {
        setConfirmToken(result.confirm_token);
        setExpectedConfirmText(result.expected_confirm_text);
        setImpactSummary(result.impact_summary);
        return;
      }

      setMessage(result.message || `已生成 ${result.insertedRows ?? rowCount} 行测试数据`);
      setConfirmToken(null);
      setConfirmText("");
      onGenerated();
    } catch (error) {
      setError(error instanceof Error ? error.message : "测试数据生成失败");
    } finally {
      setSubmitting(false);
    }
  };

  const canSubmit = !submitting && (!confirmToken || confirmText === expectedConfirmText);

  return (
    <div className="schema-dialog-backdrop">
      <div className="schema-dialog">
        <header className="schema-dialog-header">
          <div className="schema-dialog-title">
            <DatabaseZap size={16} />
            生成测试数据
          </div>
          <button className="schema-icon-button" type="button" onClick={resetAndClose} disabled={submitting}>
            <X size={15} />
          </button>
        </header>

        <div className="schema-dialog-body">
          <div className="schema-dialog-copy">
            为 <strong>{table.table_name}</strong> 生成少量模拟行，用于本地预览、联调和演示。建议只在 dev/test 数据源使用。
          </div>

          <div className="schema-dialog-grid">
            <label className="schema-dialog-field">
              <span>行数</span>
              <input
                type="number"
                min={1}
                max={500}
                value={rowCount}
                onChange={(event) => setRowCount(Math.max(1, Math.min(500, Number(event.target.value) || 1)))}
                disabled={Boolean(confirmToken) || submitting}
              />
            </label>
            <label className="schema-dialog-field">
              <span>语言</span>
              <select value={language} onChange={(event) => setLanguage(event.target.value as "zh" | "en")} disabled={Boolean(confirmToken) || submitting}>
                <option value="zh">中文</option>
                <option value="en">English</option>
              </select>
            </label>
          </div>

          {confirmToken && (
            <div className="schema-warning-box">
              <div className="schema-warning-title">
                <AlertTriangle size={15} />
                需要确认
              </div>
              <div className="schema-warning-copy">{impactSummary}</div>
              <label className="schema-dialog-field">
                <span>请输入确认文本：{expectedConfirmText}</span>
                <input value={confirmText} onChange={(event) => setConfirmText(event.target.value)} disabled={submitting} />
              </label>
            </div>
          )}

          {error && <div className="schema-error-box">{error}</div>}
          {message && <div className="schema-success-box">{message}</div>}
        </div>

        <footer className="schema-dialog-footer">
          <button className="schema-button" type="button" onClick={resetAndClose} disabled={submitting}>关闭</button>
          <button className="schema-button schema-button--primary" type="button" onClick={() => void submit()} disabled={!canSubmit}>
            {submitting && <Loader2 size={13} className="animate-spin" />}
            {confirmToken ? "确认生成" : "生成测试数据"}
          </button>
        </footer>
      </div>
    </div>
  );
}
