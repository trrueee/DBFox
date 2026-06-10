import { Sparkles } from "lucide-react";
import type { WorkspaceTab } from "../../../mock/databoxMock";

type QueryMessage = NonNullable<WorkspaceTab["chatMessages"]>[number];

export function QueryMessages({ messages }: { messages: QueryMessage[] }) {
  return (
    <>
      {messages.map((message) => (
        <div key={message.id} className={message.sender === "user" ? "hifi-user-bubble" : "hifi-ai-msg-container"}>
          {message.sender === "ai" && (
            <div className="hifi-ai-avatar">
              <Sparkles size={11} />
            </div>
          )}
          <div className={message.sender === "ai" ? "hifi-ai-msg-bubble" : ""}>{message.text}</div>
        </div>
      ))}
    </>
  );
}
