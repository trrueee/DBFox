import type { WorkspaceTab } from "../../mock/databoxMock";
import { FollowUpInput } from "./queryResult/FollowUpInput";
import { GeneratedSqlCard } from "./queryResult/GeneratedSqlCard";
import { QueryMessages } from "./queryResult/QueryMessages";
import { QueryResultHeader } from "./queryResult/QueryResultHeader";
import { TrendChartCard } from "./queryResult/TrendChartCard";

interface QueryResultWorkspaceProps {
  tab: WorkspaceTab;
  onOpenSqlConsole: () => void;
  onSetSqlQuery: (sql: string) => void;
  onSendFollowUp: (tabId: string, text: string) => void;
}

export function QueryResultWorkspace({ tab, onOpenSqlConsole, onSetSqlQuery, onSendFollowUp }: QueryResultWorkspaceProps) {
  return (
    <div className="hifi-query-result-workspace hifi-tab-pane">
      <QueryResultHeader queryText={tab.queryText || ""} />

      <div className="hifi-query-result-messages">
        <QueryMessages messages={tab.chatMessages || []} />
        <TrendChartCard />
        <GeneratedSqlCard onOpenSqlConsole={onOpenSqlConsole} onSetSqlQuery={onSetSqlQuery} />
      </div>

      <FollowUpInput tabId={tab.id} onSendFollowUp={onSendFollowUp} />
    </div>
  );
}
