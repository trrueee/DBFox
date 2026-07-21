import { SettingsStatus, SettingsToggle } from "../../components/settings";
import "./DataSourceManagement.css";

interface SchemaSyncPanelProps {
  checked: boolean;
  disabled: boolean;
  onChange: (checked: boolean) => void;
  feedback?: string | null;
  compact?: boolean;
}

export const SchemaSyncPanel = ({
  checked,
  disabled,
  onChange,
  feedback,
  compact,
}: SchemaSyncPanelProps) => (
  <div className={`ds-sync-panel${compact ? " is-compact" : ""}`}>
    <SettingsToggle
      checked={checked}
      onCheckedChange={onChange}
      disabled={disabled}
      compact={compact}
      label="AI 语义增强"
      description={compact ? undefined : "同步结构时补充业务语义，帮助 Agent 更准确地理解表和字段。"}
    />
    {feedback && !compact ? <SettingsStatus tone="info" label={feedback} /> : null}
  </div>
);
