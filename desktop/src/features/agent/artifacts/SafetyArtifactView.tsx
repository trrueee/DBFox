import { InlineSafetyBlock } from "../blocks/InlineSafetyBlock";
import type { AgentArtifact } from "../types";

export function SafetyArtifactView({ artifact }: { artifact: AgentArtifact }) {
  return <InlineSafetyBlock artifact={artifact} />;
}
