import { useState } from "react";
import { Database, RefreshCw, Trash2 } from "lucide-react";

import { Button } from "../../components/ui";
import type { DataSource } from "../../lib/api";
import { dbBadge, envBadge, fmtDate, healthType } from "./badges";
import type { ActionState } from "./formState";
import { SchemaSyncPanel } from "./SchemaSyncPanel";
import "./DataSourceManagement.css";

interface DataSourceDetailProps {
  selected: DataSource | null;
  actionState: ActionState;
  syncAiEnrich: boolean;
  lastSyncFeedback: string | null;
  onSyncAiEnrichChange: (checked: boolean) => void;
  onActivate: (datasource: DataSource) => void;
  onEdit: (datasource: DataSource) => void;
  onSyncSchema: () => void;
  onDelete: () => void;
}

const dbBadgeType = (datasource: DataSource) =>
  datasource.db_type === "postgresql" ? "postgresql" : datasource.db_type === "sqlite" ? "sqlite" : "mysql";

const envBadgeType = (env?: string) => (env === "prod" ? "prod" : env === "test" ? "test" : "dev");

export const DataSourceDetail = ({
  selected,
  actionState,
  syncAiEnrich,
  lastSyncFeedback,
  onSyncAiEnrichChange,
  onActivate,
  onEdit,
  onSyncSchema,
  onDelete,
}: DataSourceDetailProps) => {
  const [activeTab, setActiveTab] = useState<"info">("info");
  if (!selected) {
    return (
      <div className="hifi-empty-state">
        <Database size={28} />
        <p>选择一个数据源查看详情</p>
      </div>
    );
  }

  const health = healthType(selected);
  const syncingStructure = actionState === "syncing";
  const detailActionBusy = actionState !== "idle";
  const badge = dbBadge(selected);
  const environment = envBadge(selected.env);
  const dbType = dbBadgeType(selected);
  const environmentType = envBadgeType(selected.env);

  return (
    <div className="hifi-datasource-detail ds-detail">
      <div className="ds-detail-header">
        <div className="ds-detail-identity">
          <div className={`ds-detail-icon ds-detail-icon--${dbType}`}>
            <Database size={22} />
          </div>
          <div className="ds-detail-title-block">
            <div className="ds-detail-title-row">
              <h3 className="ds-detail-title">{selected.name}</h3>
              <span className={`ds-detail-badge ds-detail-badge--${dbType}`}>{badge.label}</span>
              <span className={`ds-detail-badge ds-detail-badge--${environmentType}`}>
                {environment.label}
              </span>
              {selected.is_read_only && <span className="ds-detail-badge ds-detail-badge--readonly">只读</span>}
            </div>
            <div className="ds-detail-path">
              {selected.db_type === "sqlite"
                ? selected.database_name
                : `${selected.host}:${selected.port} / ${selected.database_name}`}
            </div>
          </div>
        </div>
        <div className="ds-detail-actions">
          <SchemaSyncPanel
            checked={syncAiEnrich}
            onChange={onSyncAiEnrichChange}
            disabled={detailActionBusy}
            compact
          />
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="ds-detail-button"
            onClick={() => onActivate(selected)}
            disabled={detailActionBusy}
          >
            设为当前
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="ds-detail-button"
            onClick={() => onEdit(selected)}
            disabled={detailActionBusy}
          >
            编辑
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="ds-detail-button"
            onClick={onSyncSchema}
            disabled={detailActionBusy}
            title="重新读取表、字段、主外键和注释等结构信息"
          >
            <RefreshCw className={`ds-detail-button-icon${syncingStructure ? " is-spinning" : ""}`} />
            {syncingStructure ? "同步中" : "同步结构"}
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="ds-detail-button ds-detail-button--danger"
            onClick={onDelete}
            disabled={detailActionBusy}
          >
            <Trash2 className="ds-detail-button-icon" />
            删除
          </Button>
        </div>
      </div>

      <div className="ds-detail-tabs">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => setActiveTab("info")}
          className={`ds-detail-tab${activeTab === "info" ? " is-active" : ""}`}
        >
          基本信息
        </Button>
      </div>

      {activeTab === "info" && (
        <div className="ds-detail-section-stack">
          <section>
            <h4 className="field-label ds-detail-section-heading">连接配置摘要</h4>
            <div className="ds-detail-summary-grid">
              <SummaryTile label="主机地址" value={selected.db_type === "sqlite" ? "N/A (本地文件)" : selected.host || "-"} />
              <SummaryTile label="端口" value={selected.db_type === "sqlite" ? "N/A" : selected.port || "-"} />
              <SummaryTile label="数据库名" value={selected.database_name || "-"} />
              <SummaryTile label="连接用户名" value={selected.db_type === "sqlite" ? "N/A" : selected.username || "-"} />
            </div>
            {lastSyncFeedback && (
              <div className="ds-detail-sync-feedback">
                <SchemaSyncPanel
                  checked={syncAiEnrich}
                  onChange={onSyncAiEnrichChange}
                  disabled={detailActionBusy}
                  feedback={lastSyncFeedback}
                />
              </div>
            )}
          </section>

          <section>
            <h4 className="field-label ds-detail-section-heading">状态与同步</h4>
            <div className="ds-detail-summary-grid">
              <HealthTile health={health} selected={selected} />
              <SummaryTile label="数据表数量" value={`${selected.last_test_tables_count ?? "-"} 张表`} emphasized />
              <SummaryTile label="上次结构同步" value={fmtDate(selected.last_sync_at)} />
            </div>
          </section>

          {selected.last_test_error && (
            <div className="ds-detail-error">
              <div className="ds-detail-error-title">连接异常信息:</div>
              <div className="ds-detail-error-body">{selected.last_test_error}</div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

const SummaryTile = ({
  label,
  value,
  emphasized,
}: {
  label: string;
  value: string | number;
  emphasized?: boolean;
}) => (
  <div className="ds-detail-tile">
    <div className="ds-detail-tile__label">{label}</div>
    <div className={`ds-detail-tile__value${emphasized ? " ds-detail-tile__value--emphasized" : ""}`}>
      {value}
    </div>
  </div>
);

const healthLabel = (health: "success" | "error" | "idle") => {
  if (health === "success") return "正常";
  if (health === "error") return "失败";
  return "未检测";
};

const HealthTile = ({ health, selected }: { health: "success" | "error" | "idle"; selected: DataSource }) => (
  <div className="ds-detail-tile ds-detail-health">
    <div className="ds-detail-tile__label">连接状态</div>
    <div className="ds-detail-health__row">
      <span className={`ds-detail-health__dot ds-detail-health__dot--${health}`} />
      <span className={`ds-detail-health__text ds-detail-health__text--${health}`}>{healthLabel(health)}</span>
      {health === "success" && selected.last_test_latency_ms ? (
        <span className="ds-detail-health__latency">({selected.last_test_latency_ms}ms)</span>
      ) : null}
    </div>
  </div>
);
