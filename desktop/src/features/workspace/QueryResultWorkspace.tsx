import { Send, Sparkles, Terminal, TrendingUp } from "lucide-react";
import { generatedSql, type WorkspaceTab } from "../../mock/databoxMock";

interface QueryResultWorkspaceProps {
  tab: WorkspaceTab;
  onOpenSqlConsole: () => void;
  onSetSqlQuery: (sql: string) => void;
  onSendFollowUp: (tabId: string, text: string) => void;
}

export function QueryResultWorkspace({ tab, onOpenSqlConsole, onSetSqlQuery, onSendFollowUp }: QueryResultWorkspaceProps) {
  const queryText = tab.queryText || "";
  const messages = tab.chatMessages || [];

  return (
    <div className="hifi-query-result-workspace hifi-tab-pane">
      <div className="hifi-query-result-header">
        <div className="flex items-center gap-2 text-[10px] text-slate-500 mb-1">
          <TrendingUp size={11} className="text-purple-500" />
          <span>智能问数分析结果</span>
        </div>
        <h3 className="font-bold text-[12px] text-slate-800">“{queryText}”</h3>
      </div>

      <div className="hifi-query-result-messages">
        {messages.map((message) => (
          <div key={message.id} className={message.sender === "user" ? "hifi-user-bubble" : "hifi-ai-msg-container"}>
            {message.sender === "ai" && <div className="hifi-ai-avatar"><Sparkles size={11} /></div>}
            <div className={message.sender === "ai" ? "hifi-ai-msg-bubble" : ""}>{message.text}</div>
          </div>
        ))}

        <div className="hifi-ai-card mt-2">
          <div className="hifi-ai-card-header flex justify-between items-center">
            <span>数据趋势分析</span>
            <span className="hifi-guide-chip-prod">LINE CHART</span>
          </div>
          <div className="hifi-ai-card-body p-3">
            <svg viewBox="0 0 400 120" width="100%" height="100">
              <line x1="30" y1="20" x2="380" y2="20" stroke="#F1F5F9" strokeWidth="1" />
              <line x1="30" y1="50" x2="380" y2="50" stroke="#F1F5F9" strokeWidth="1" />
              <line x1="30" y1="80" x2="380" y2="80" stroke="#F1F5F9" strokeWidth="1" />
              <line x1="30" y1="100" x2="380" y2="100" stroke="#E2E8F0" strokeWidth="1.5" />
              <text x="5" y="23" fontSize="8" fill="#64748B">1.5K</text>
              <text x="10" y="53" fontSize="8" fill="#64748B">1K</text>
              <text x="10" y="83" fontSize="8" fill="#64748B">500</text>
              <text x="20" y="103" fontSize="8" fill="#64748B">0</text>
              <defs><linearGradient id="glow-grad" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#4F46E5" stopOpacity="0.25" /><stop offset="100%" stopColor="#4F46E5" stopOpacity="0.0" /></linearGradient></defs>
              <path d="M 30 100 Q 60 70 90 85 Q 130 40 160 90 Q 210 50 250 80 Q 300 30 380 60 L 380 100 Z" fill="url(#glow-grad)" />
              <path d="M 30 100 Q 60 70 90 85 Q 130 40 160 90 Q 210 50 250 80 Q 300 30 380 60" fill="none" stroke="#4F46E5" strokeWidth="2.5" />
              <circle cx="90" cy="85" r="3" fill="#FFFFFF" stroke="#4F46E5" strokeWidth="1.5" />
              <circle cx="160" cy="90" r="3" fill="#FFFFFF" stroke="#4F46E5" strokeWidth="1.5" />
              <circle cx="250" cy="80" r="3" fill="#FFFFFF" stroke="#4F46E5" strokeWidth="1.5" />
              <circle cx="380" cy="60" r="3" fill="#FFFFFF" stroke="#4F46E5" strokeWidth="1.5" />
            </svg>
          </div>
        </div>

        <div className="hifi-ai-card">
          <div className="hifi-ai-card-header">生成的 SQL 查询</div>
          <div className="hifi-ai-card-body">
            <pre className="hifi-sql-card font-mono text-[10px] leading-relaxed p-3 text-slate-800">{generatedSql}</pre>
            <div className="hifi-sql-card-action">
              <button
                className="hifi-guide-btn-secondary flex items-center gap-1"
                style={{ height: "24px", fontSize: "10px" }}
                onClick={() => {
                  onSetSqlQuery(generatedSql);
                  onOpenSqlConsole();
                }}
              >
                <Terminal size={10} />
                在 SQL 工作台打开
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="hifi-query-result-footer">
        <div className="hifi-chat-input-wrapper">
          <input
            type="text"
            className="hifi-chat-input"
            placeholder="针对此问数结果继续追问..."
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                onSendFollowUp(tab.id, (event.target as HTMLInputElement).value);
                (event.target as HTMLInputElement).value = "";
              }
            }}
          />
          <button className="hifi-chat-send-btn"><Send size={13} /></button>
        </div>
      </div>
    </div>
  );
}
