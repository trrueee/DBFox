import type { WorkspaceTab } from "../../../mock/dbfoxMock";
import { FoxIcon } from "../../../components/brand/FoxIcon";
import { MarkdownContent } from "./MarkdownContent";

type QueryMessage = NonNullable<WorkspaceTab["chatMessages"]>[number];

export function QueryMessages({ messages }: { messages: QueryMessage[] }) {
  return (
    <>
      {messages.map((message) => (
        <div key={message.id} className={message.sender === "user" ? "hifi-user-bubble" : "hifi-ai-msg-container"}>
          {message.sender === "ai" && (
            <div className="hifi-ai-avatar">
              <FoxIcon variant="ai-tight" size={18} alt="DBFox AI" />
            </div>
          )}
          <div className={message.sender === "ai" ? "hifi-ai-msg-bubble" : ""}>
            {message.sender === "ai" ? <MarkdownContent content={message.text} /> : message.text}
          </div>
        </div>
      ))}
    </>
  );
}
