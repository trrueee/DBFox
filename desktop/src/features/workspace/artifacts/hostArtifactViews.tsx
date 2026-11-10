import { DATAFRAME_REPRESENTATION_TYPE } from "../../../lib/api/representation";
import { TableArtifactView } from "./TableArtifactView";
import type { ArtifactViewContribution } from "./types";
import { asRecord } from "./types";
import { CORE_ARTIFACT_VIEW_IDS } from "../../dlc/coreContributionIds";
import { EXECUTION_LOG_REPRESENTATION, ExecutionArtifactView } from "./ExecutionArtifactView";

/**
 * Reusable Host projections selected only by public Representation support.
 * Domain Artifact selectors and semantics remain in their owning DLC.
 */
export const hostArtifactViews: ReadonlyArray<ArtifactViewContribution<unknown>> = [
  {
    id: CORE_ARTIFACT_VIEW_IDS.executionLog,
    title: "运行输出",
    priority: 90,
    surfaces: ["workspace"],
    representationTypes: [EXECUTION_LOG_REPRESENTATION],
    parsePayload: asRecord,
    render: (artifact, _payload, context) => <ExecutionArtifactView artifact={artifact} context={context} />,
  },
  {
    id: CORE_ARTIFACT_VIEW_IDS.dataframeTable,
    title: "表格",
    priority: 90,
    surfaces: ["inline", "workspace"],
    representationTypes: [DATAFRAME_REPRESENTATION_TYPE],
    parsePayload: asRecord,
    render: (artifact, _payload, context) => (
      <TableArtifactView
        artifact={artifact}
        onToast={context.onToast}
        onOpenArtifact={context.openArtifact}
        mode={context.surface}
      />
    ),
  },
];
