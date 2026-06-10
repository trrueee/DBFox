import { Bell, Search } from "lucide-react";

interface HeaderProps {
  activeHeaderTab: string;
  onHeaderTabChange: (tab: string) => void;
}

const headerTabs = [
  { id: "workbench", label: "工作台" },
  { id: "database", label: "数据库" },
  { id: "ask", label: "智能问数" },
  { id: "datasource", label: "数据源管理" },
];

export function Header({ activeHeaderTab, onHeaderTabChange }: HeaderProps) {
  return (
    <header className="hifi-header">
      <div className="hifi-header-left">
        <h1 className="hifi-header-title">数据库可视化 + 智能问数</h1>
        <span className="hifi-header-subtitle">全新界面设计方案</span>
      </div>

      <div className="hifi-header-tabs">
        {headerTabs.map((tab) => (
          <div
            key={tab.id}
            className={`hifi-header-tab ${activeHeaderTab === tab.id ? "active" : ""}`}
            onClick={() => onHeaderTabChange(tab.id)}
          >
            {tab.label}
          </div>
        ))}
      </div>

      <div className="hifi-header-right">
        <div className="hifi-icon-btn">
          <Search size={16} />
        </div>
        <div className="hifi-icon-btn">
          <Bell size={16} />
        </div>
        <div className="hifi-avatar">A</div>
      </div>
    </header>
  );
}
