import { InlineChartBlock } from "../blocks/InlineChartBlock";
import type { AgentArtifact } from "../types";

export function ChartArtifactView({ artifact }: { artifact: AgentArtifact }) {
  return <InlineChartBlock artifact={artifact} />;
}
