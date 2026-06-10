import type { WorkspaceTab } from "../../mock/databoxMock";
import { ArtifactRenderer } from "./artifacts/ArtifactRenderer";
import { FollowUpInput } from "./queryResult/FollowUpInput";
import { QueryMessages } from "./queryResult/QueryMessages";
import { QueryResultHeader } from "./queryResult/QueryResultHeader";

interface QueryResultWorkspaceProps {
  tab: WorkspaceTab;
  onOpenSqlConsole: () => void;
  onSetSqlQuery: (sql: string) => void;
  onSendFollowUp: (tabId: string, text: string) => void;
  onToast: (message: string) => void;
}

export function QueryResultWorkspace({ tab, onOpenSqlConsole, onSetSqlQuery, onSendFollowUp, onToast }: QueryResultWorkspaceProps) {
  return (
    <div className="hifi-query-result-workspace hifi-tab-pane">
      <QueryResultHeader queryText={tab.queryText || ""} />

      <div className="hifi-query-result-messages">
        <QueryMessages messages={tab.chatMessages || []} />
        <ArtifactRenderer
          artifacts={tab.artifacts ?? []}
          onOpenSqlConsole={onOpenSqlConsole}
          onSetSqlQuery={onSetSqlQuery}
          onToast={onToast}
        />
      </div>

      <FollowUpInput tabId={tab.id} onSendFollowUp={onSendFollowUp} />
    </div>
  );
}
