import type { AgentRunStatus } from "../../types/conversation";
import { runPresentation } from "./runPresentation";
import "./thread-beacon.css";

export function ThreadBeacon({ status, decorative = false }: { status?: AgentRunStatus | null; decorative?: boolean }) {
  const { icon: Icon, label, tone } = runPresentation(status);
  return <span className="thread-beacon" data-state={status ?? "idle"} data-tone={tone}
    role={decorative ? undefined : "img"} aria-label={decorative ? undefined : label}
    aria-hidden={decorative || undefined} title={label}>
    <Icon size={16} weight={tone === "attention" || tone === "danger" ? "fill" : "regular"} aria-hidden="true" />
  </span>;
}
