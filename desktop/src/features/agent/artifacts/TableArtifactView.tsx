import { InlineTableBlock } from "../blocks/InlineTableBlock";
import type { AgentArtifact } from "../types";

export function TableArtifactView({ artifact }: { artifact: AgentArtifact }) {
  return <InlineTableBlock artifact={artifact} />;
}
