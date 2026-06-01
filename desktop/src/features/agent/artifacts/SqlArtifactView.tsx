import { InlineSqlBlock } from "../blocks/InlineSqlBlock";
import type { AgentArtifact } from "../types";

export function SqlArtifactView({ artifact, onOpenSql }: { artifact: AgentArtifact; onOpenSql?: (sql: string) => void }) {
  return <InlineSqlBlock artifact={artifact} onOpenSql={onOpenSql} />;
}
