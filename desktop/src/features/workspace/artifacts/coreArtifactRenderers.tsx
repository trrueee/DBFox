import { MarkdownArtifactView } from "./MarkdownArtifactView";
import type {
  ArtifactRendererContribution,
} from "./types";
import { asRecord } from "./types";
import type { MarkdownArtifact } from "../../../types/agentArtifact";

function parseMarkdownPayload(value: unknown): MarkdownArtifact {
  const payload = asRecord(value);
  const content =
    typeof payload.content === "string"
      ? payload.content
      : typeof payload.markdown === "string"
        ? payload.markdown
        : "";
  return {
    id: "",
    type: "markdown",
    schemaVersion: 1,
    title: "",
    content,
  };
}

export const coreArtifactRenderers: ReadonlyArray<
  ArtifactRendererContribution<unknown>
> = [
  {
    type: "markdown",
    supportedSchemaVersions: [1],
    parsePayload: parseMarkdownPayload,
    render: (artifact, context) => {
      const model = {
        ...parseMarkdownPayload(artifact.payload),
        id: artifact.id,
        title: artifact.title,
      };
      return <MarkdownArtifactView artifact={model} onToast={context.onToast} />;
    },
  },
];
