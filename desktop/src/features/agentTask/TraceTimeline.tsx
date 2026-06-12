import { useEffect, useRef } from "react";
import { User } from "lucide-react";
import type { AgentTimelineItem } from "../workspace/agentTimeline";
import type { AgentTabStatus } from "../../mock/databoxMock";
import { ToolCallCard } from "./ToolCallCard";
import { ThinkingStep } from "./ThinkingStep";

interface TraceTimelineProps {
  items: AgentTimelineItem[];
  agentStatus: AgentTabStatus;
  isRunning: boolean;
}

export function TraceTimeline({ items, agentStatus, isRunning }: TraceTimelineProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const lastCountRef = useRef(items.length);

  // Auto-scroll to bottom when new items arrive during running
  useEffect(() => {
    if (isRunning && items.length > lastCountRef.current && scrollRef.current) {
      scrollRef.current.scrollTo({
        top: scrollRef.current.scrollHeight,
        behavior: "smooth",
      });
    }
    lastCountRef.current = items.length;
  }, [items.length, isRunning]);

  if (items.length === 0) return null;

  return (
    <div className="task-trace-timeline" ref={scrollRef}>
      {/* Vertical rail connector */}
      <div className="task-trace-rail" />

      {items.map((item, index) => {
        const isLatest = index === items.length - 1 && isRunning;
        return <TraceTimelineRow key={item.id} item={item} isLatest={isLatest} />;
      })}
    </div>
  );
}

function TraceTimelineRow({ item, isLatest }: { item: AgentTimelineItem; isLatest: boolean }) {
  // User message row — simple card
  if (item.kind === "user") {
    return (
      <div className="task-trace-row">
        <div className="task-trace-dot task-trace-dot-info">
          <User size={11} className="text-slate-500" />
        </div>
        <div className="task-trace-card task-trace-card-user">
          <div className="task-trace-card-header">
            <span className="task-trace-card-title">用户问题</span>
          </div>
          {item.content && (
            <div className="task-trace-card-body">
              <p className="task-trace-user-text">{item.content}</p>
            </div>
          )}
        </div>
      </div>
    );
  }

  // Assistant message row — thinking step
  if (item.kind === "assistant") {
    return (
      <ThinkingStep
        content={item.content || ""}
        status={item.status === "running" ? "running" : "info"}
        isLatest={isLatest}
      />
    );
  }

  // Tool call row
  return (
    <ToolCallCard
      data={{
        toolName: item.toolName || "tool",
        title: item.title,
        subtitle: item.subtitle,
        status: (item.status === "running" || item.status === "success" || item.status === "failed" || item.status === "skipped")
          ? item.status as "running" | "success" | "failed" | "skipped"
          : "success",
        input: item.input,
        output: item.output,
        error: item.error,
        latencyMs: item.latencyMs,
      }}
      isLatest={isLatest}
    />
  );
}
