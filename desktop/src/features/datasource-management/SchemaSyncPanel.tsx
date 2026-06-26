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
    <label className={`field-label ds-sync-panel__label${disabled ? " is-disabled" : ""}`}>
      <input
        type="checkbox"
        className="ds-sync-panel__checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        disabled={disabled}
      />
      AI 语义增强
    </label>
    {feedback && !compact && (
      <div role="status" className="ds-sync-panel__feedback">
        {feedback}
      </div>
    )}
  </div>
);
