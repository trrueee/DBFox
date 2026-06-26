import { Copy } from "lucide-react";
import { Button } from "../../../components/ui";
import type { MarkdownArtifact } from "../../../types/agentArtifact";
import { MarkdownContent } from "../queryResult/MarkdownContent";
import { ArtifactCard } from "./ArtifactCard";
import { copyText } from "./artifactActions";
import "./ArtifactViews.css";

interface MarkdownArtifactViewProps {
  artifact: MarkdownArtifact;
  onToast: (message: string) => void;
}

export function MarkdownArtifactView({ artifact, onToast }: MarkdownArtifactViewProps) {
  const handleCopy = async () => {
    const ok = await copyText(artifact.content);
    onToast(ok ? "已复制" : "复制失败");
  };

  return (
    <ArtifactCard
      title={artifact.title}
      badge="分析"
      tone="insight"
      description={artifact.description}
      actions={
        <Button type="button" variant="outline" size="sm" className="artifact-action-button" onClick={handleCopy}>
          <Copy size={10} />
          复制
        </Button>
      }
    >
      <MarkdownContent content={artifact.content} />
    </ArtifactCard>
  );
}
