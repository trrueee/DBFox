import { Database, Search } from "lucide-react";

import { Input } from "../../components/ui";
import type { DataSource } from "../../lib/api";
import { dbBadge, envBadge, healthType } from "./badges";
import "./DataSourceManagement.css";

interface DataSourceListProps {
  datasources: DataSource[];
  selectedId: string;
  search: string;
  onSearchChange: (value: string) => void;
  onSelect: (id: string) => void;
}

const dbBadgeType = (datasource: DataSource) =>
  datasource.db_type === "postgresql" ? "postgresql" : datasource.db_type === "sqlite" ? "sqlite" : "mysql";

const envBadgeType = (env?: string) => (env === "prod" ? "prod" : env === "test" ? "test" : "dev");

export const DataSourceList = ({
  datasources,
  selectedId,
  search,
  onSearchChange,
  onSelect,
}: DataSourceListProps) => {
  const searchTerm = search.toLowerCase();
  const filtered = searchTerm
    ? datasources.filter(
        (datasource) =>
          datasource.name.toLowerCase().includes(searchTerm) ||
          (datasource.host ?? "").toLowerCase().includes(searchTerm),
      )
    : datasources;

  return (
    <div className="hifi-datasource-list">
      <div className="ds-management-search-bar">
        <div className="ds-management-search-shell">
          <Search size={12} className="ds-management-search-icon" />
          <Input
            className="ds-management-search-input"
            placeholder="搜索连接…"
            value={search}
            onChange={(event) => onSearchChange(event.target.value)}
          />
        </div>
      </div>
      <div className="ds-management-list-scroll">
        {filtered.map((datasource) => {
          const isSelected = datasource.id === selectedId;
          const health = healthType(datasource);

          return (
            <button
              key={datasource.id}
              className={`hifi-datasource-list-item${isSelected ? " active" : ""}`}
              onClick={() => onSelect(datasource.id)}
            >
              <div className="ds-management-list-item-main">
                <Database size={12} className={`ds-management-list-icon${isSelected ? " is-active" : ""}`} />
                <span className="ds-management-list-item-title">{datasource.name}</span>
              </div>
              <div className="ds-management-list-item-meta">
                <span className={`ds-management-badge ds-management-badge--${dbBadgeType(datasource)}`}>
                  {dbBadge(datasource).label}
                </span>
                <span className={`ds-management-badge ds-management-badge--${envBadgeType(datasource.env)}`}>
                  {envBadge(datasource.env).label}
                </span>
                <span className={`ds-management-health-dot ds-management-health-dot--${health}`} />
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
};
