import { useState } from "react";
import { Bot, CheckCircle2, ChevronDown, ChevronRight, Clock, User, Wrench, XCircle } from "lucide-react";
import type { AgentTimelineItem } from "../agentTimeline";
import { MarkdownContent } from "./MarkdownContent";

export function AgentTimelineView({ items }: { items: AgentTimelineItem[] }) {
  if (items.length === 0) return null;

  return (
    <div className="hifi-agent-timeline">
      {items.map((item) => (
        <AgentTimelineRow key={item.id} item={item} />
      ))}
    </div>
  );
}

function AgentTimelineRow({ item }: { item: AgentTimelineItem }) {
  const [expanded, setExpanded] = useState(item.status === "failed");
  const expandable = item.kind === "tool" && Boolean(item.input || item.output || item.error);

  return (
    <div className={`hifi-agent-timeline-row hifi-agent-timeline-${item.kind}`}>
      <div className={`hifi-agent-timeline-icon hifi-agent-timeline-status-${item.status}`}>
        {iconFor(item.kind, item.status)}
      </div>
      <div className="hifi-agent-timeline-card">
        <button
          className="hifi-agent-timeline-head"
          onClick={() => expandable && setExpanded((value) => !value)}
          disabled={!expandable}
        >
          <span className="hifi-agent-timeline-title">{item.title}</span>
          {item.subtitle && <span className="hifi-agent-timeline-subtitle">{item.subtitle}</span>}
          {typeof item.latencyMs === "number" && (
            <span className="hifi-agent-timeline-latency">
              <Clock size={10} />
              {formatLatency(item.latencyMs)}
            </span>
          )}
          {expandable && (
            <span className="hifi-agent-timeline-expand">
              {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            </span>
          )}
        </button>

        {item.content && (
          <div className="hifi-agent-timeline-content">
            <MarkdownContent content={item.content} />
          </div>
        )}

        {expandable && expanded && (
          <div className="hifi-agent-timeline-detail">
            {item.input && <JsonBlock title="Input" value={item.input} />}
            {item.output && <JsonBlock title="Output" value={item.output} />}
            {item.error && <JsonBlock title="Error" value={item.error} danger />}
          </div>
        )}
      </div>
    </div>
  );
}

function JsonBlock({ title, value, danger = false }: { title: string; value: unknown; danger?: boolean }) {
  return (
    <div className={`hifi-agent-json-block ${danger ? "hifi-agent-json-danger" : ""}`}>
      <div className="hifi-agent-json-title">{title}</div>
      <pre>{formatJson(value)}</pre>
    </div>
  );
}

function iconFor(kind: AgentTimelineItem["kind"], status: AgentTimelineItem["status"]) {
  if (status === "failed") return <XCircle size={13} />;
  if (status === "success") return <CheckCircle2 size={13} />;
  if (kind === "user") return <User size={13} />;
  if (kind === "tool") return <Wrench size={13} />;
  return <Bot size={13} />;
}

function formatLatency(ms: number) {
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.max(0, Math.round(ms))}ms`;
}

function formatJson(value: unknown): string {
  if (typeof value === "string") return value;
  return JSON.stringify(value, null, 2);
}
