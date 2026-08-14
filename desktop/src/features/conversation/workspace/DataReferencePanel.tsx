import { BarChart2, Braces, Database, Table2 } from "lucide-react";
import type { ConversationArtifact } from "../../../types/conversation";
import type { DataReference } from "../../../types/agentArtifact";
import { buildDataReferences, referenceKey, referenceTitle } from "./dataReferences";

interface DataReferencePanelProps {
  artifacts: ConversationArtifact[];
  kind?: "evidence" | "saved";
  onSelectArtifact?: (artifactId: string) => void;
}

export function DataReferencePanel({
  artifacts,
  kind = "evidence",
  onSelectArtifact,
}: DataReferencePanelProps) {
  const references = buildDataReferences(artifacts);
  if (references.length === 0) return null;
  const label = kind === "evidence" ? "引用的数据来源" : "已保存结果";

  return (
    <div className="conv-data-refs" aria-label={label} data-reference-kind={kind}>
      <span className="conv-data-refs-label">{label}</span>
      <div className="conv-data-ref-list">
        {references.map((reference) => (
          <button
            key={referenceKey(reference)}
            type="button"
            className={`conv-data-ref conv-data-ref-${reference.type}`}
            onClick={() => {
              if ("artifactId" in reference && reference.artifactId && onSelectArtifact) {
                onSelectArtifact(reference.artifactId);
                return;
              }
            }}
            title={referenceTitle(reference)}
          >
            {referenceIcon(reference.type)}
            <span>{reference.label}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

function referenceIcon(type: DataReference["type"]) {
  if (type === "table") return <Database size={12} />;
  if (type === "column") return <Braces size={12} />;
  if (type === "chart") return <BarChart2 size={12} />;
  return <Table2 size={12} />;
}
