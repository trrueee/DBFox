import { useCallback } from "react";
import { FileTextIcon } from "@/components/icons";
import { Button } from "../../../components/ui";
import { zJobPage } from "../../../lib/api/generated/zod.gen";
import { ExecutionLogView } from "../../dock/ExecutionLogView";
import type { ArtifactEnvelope, ArtifactViewContext } from "./types";

export const EXECUTION_LOG_REPRESENTATION = "dbfox.workspace.execution_log.v1";

export function ExecutionArtifactView({ artifact, context }: {
  artifact: ArtifactEnvelope<unknown>;
  context: ArtifactViewContext;
}) {
  const readArtifact = context.representations.read;
  const read = useCallback(async (after: number, tail: boolean, signal: AbortSignal) => {
    const page = await readArtifact(artifact.id, EXECUTION_LOG_REPRESENTATION, {
      operation: "page", parameters: { after, tail, limit: 16 },
    }, signal);
    return zJobPage.parse(page.payload);
  }, [artifact.id, readArtifact]);
  return <>
    <ExecutionLogView key={artifact.id} read={read} />
    {context.openArtifact && artifact.relations?.some(item => item.relation === "supports") ? (
      <ul className="m-0 flex list-none flex-wrap gap-1 px-4 pb-4" aria-label="关联项目文件">
        {artifact.relations.filter(item => item.relation === "supports").map((item, index) => {
          const related = context.resolveArtifact?.(item.artifact_id) ?? {
            id: item.artifact_id, type: "dbfox.workspace.file_snapshot", title: "关联文件 " + (index + 1),
          };
          return <li key={item.artifact_id}><Button type="button" variant="ghost" size="sm"
            onClick={() => context.openArtifact?.(related)}>
            <FileTextIcon aria-hidden="true" />{related.title}
          </Button></li>;
        })}
      </ul>
    ) : null}
  </>;
}
