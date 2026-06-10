import { Database, Sparkles, Terminal } from "lucide-react";
import type { DataSource, SchemaTable } from "../../lib/api";

interface WorkbenchHomeProps {
  datasource: DataSource | null;
  tables: SchemaTable[];
  onOpenQuery: () => void;
  onOpenDataSources: () => void;
  onOpenTable: (tableName: string) => void;
}

export function WorkbenchHome({ datasource, tables, onOpenQuery, onOpenDataSources, onOpenTable }: WorkbenchHomeProps) {
  return (
    <div className="workbench-home">
      <div className="workbench-home__card">
        <div className="workbench-home__icon"><Database size={28} /></div>
        <div>
          <p className="workbench-home__eyebrow">DataBox Workbench</p>
          <h1>数据库可视化工作台</h1>
          <p>
            当前阶段先把看表、看字段、看关系的主链路做稳。SQL 控制台和 Agent Copilot 保持为工作台能力，而不是挤占主视觉。
          </p>
        </div>

        <div className="workbench-home__actions">
          <button className="primary-button" onClick={onOpenQuery} disabled={!datasource}>
            <Terminal size={15} /> 新建 SQL 控制台
          </button>
          <button className="secondary-button" onClick={onOpenDataSources}>
            <Database size={15} /> 连接管理
          </button>
        </div>

        {datasource ? (
          <div className="workbench-home__tables">
            <div className="workbench-home__tables-title">
              <Sparkles size={14} /> 快速打开数据表
            </div>
            {tables.length === 0 ? (
              <div className="workbench-home__empty">当前连接暂未同步到表结构。</div>
            ) : (
              <div className="workbench-home__grid">
                {tables.slice(0, 12).map((table) => (
                  <button key={table.id} onClick={() => onOpenTable(table.table_name)} title={table.table_comment || table.table_name}>
                    <span>{table.table_name}</span>
                    {table.table_comment && <small>{table.table_comment}</small>}
                  </button>
                ))}
              </div>
            )}
          </div>
        ) : (
          <div className="workbench-home__empty">请先创建或选择一个数据源。</div>
        )}
      </div>
    </div>
  );
}
