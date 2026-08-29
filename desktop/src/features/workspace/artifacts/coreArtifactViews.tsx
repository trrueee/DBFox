import {
  MarkdownArtifactView,
  type MarkdownArtifactViewModel,
} from "./MarkdownArtifactView";
import type {
  ArtifactViewContribution,
} from "./types";
import { asRecord } from "./types";
import { CORE_ARTIFACT_VIEW_IDS } from "../../dlc/coreContributionIds";

function parseMarkdownPayload(value: unknown): MarkdownArtifactViewModel {
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
    title: "",
    content,
  };
}

export const coreArtifactViews: ReadonlyArray<
  ArtifactViewContribution<unknown>
> = [
  {
    id: CORE_ARTIFACT_VIEW_IDS.markdown,
    title: "文档",
    priority: 50,
    surfaces: ["inline", "workspace"],
    artifactTypes: [{ type: "markdown", schemaVersions: [1] }],
    parsePayload: parseMarkdownPayload,
    render: (artifact, payload, context) => {
      const model = {
        ...(payload as MarkdownArtifactViewModel),
        id: artifact.id,
        title: artifact.title,
      };
      return <MarkdownArtifactView artifact={model} onToast={context.onToast} />;
    },
  },
];
