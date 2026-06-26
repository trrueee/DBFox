import { useState } from "react";
import { GitMerge } from "lucide-react";
import { Button, EmptyState, Input } from "../../components/ui";
import { WorkspaceShell } from "../appShell/WorkspaceShell";
import "./MultiTableWorkspace.css";

interface MultiTableWorkspaceProps {
  tables: string[];
  onOpenQueryResult: (query: string) => void;
  onToast: (message: string) => void;
}

export function MultiTableWorkspace({ tables, onOpenQueryResult, onToast }: MultiTableWorkspaceProps) {
  const [customQuery, setCustomQuery] = useState("");
  const selectedTables = tables.join("，");
  const promptPlaceholder = `例如：帮我查询在 ${tables.slice(0, 2).join("和")} 之间进行内连接关联的数据...`;

  const submitCustomQuery = () => {
    const query = customQuery.trim();
    if (!query) {
      onToast("请输入联合分析问题");
      return;
    }
    onOpenQueryResult(query);
    setCustomQuery("");
  };

  if (tables.length === 0) {
    return (
      <WorkspaceShell
        className="multi-table-workspace"
        title="联合 Workspace"
        description="把多张表作为同一个分析上下文，生成跨表查询和结构洞察。"
        bodyClassName="multi-table-workspace__body"
      >
        <EmptyState
          title="还没有选择表"
          description="从左侧数据源树选择多个表后，可以在这里发起联合分析。"
        />
      </WorkspaceShell>
    );
  }

  return (
    <WorkspaceShell
      className="multi-table-workspace"
      title={`联合 Workspace (${tables.length} 张表)`}
      description="跨表查看关系、趋势和自然语言查询上下文。"
      bodyClassName="multi-table-workspace__body"
    >
      <div className="multi-table-workspace__summary">
        <GitMerge size={16} className="multi-table-workspace__summary-icon" aria-hidden="true" />
        <div>
          <span className="multi-table-workspace__summary-title">已绑定 {tables.length} 张表</span>
          <span className="multi-table-workspace__summary-copy">{selectedTables}</span>
        </div>
      </div>

      <div className="multi-table-workspace__actions">
        <button
          type="button"
          className="multi-table-workspace__action"
          onClick={() => onOpenQueryResult(`查询这 ${tables.length} 张表的关联性，并给出数据字典`)}
        >
          <span className="multi-table-workspace__action-title">分析表关联拓扑图</span>
          <span className="multi-table-workspace__action-copy">计算表与表之间的物理键及逻辑外键联系。</span>
        </button>
        <button
          type="button"
          className="multi-table-workspace__action"
          onClick={() => onOpenQueryResult(`统计所选表在最近一月的联合活动数据量`)}
        >
          <span className="multi-table-workspace__action-title">联合数据趋势统计</span>
          <span className="multi-table-workspace__action-copy">分析用户、评论、流量记录的联合转化率。</span>
        </button>
      </div>

      <section className="multi-table-workspace__prompt" aria-labelledby="multi-table-prompt-title">
        <label className="multi-table-workspace__prompt-title" id="multi-table-prompt-title" htmlFor="multi-table-question">
          针对选定的 {tables.length} 张表进行智能提问
        </label>
        <div className="multi-table-workspace__prompt-row">
          <Input
            id="multi-table-question"
            aria-label="联合分析问题"
            value={customQuery}
            placeholder={promptPlaceholder}
            onChange={(event) => setCustomQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                submitCustomQuery();
              }
            }}
          />
          <Button type="button" onClick={submitCustomQuery}>
            联合分析
          </Button>
        </div>
      </section>
    </WorkspaceShell>
  );
}
