import { apiListProjectResourcesApiV1ProjectsProjectIdResourcesGet } from "../../lib/api/generated/sdk.gen";
import type { ProjectResourceDescriptor } from "../../lib/api/generated/types.gen";

export async function listProjectResources(
  projectId: string,
): Promise<ProjectResourceDescriptor[]> {
  const { data } = await apiListProjectResourcesApiV1ProjectsProjectIdResourcesGet({
    path: { project_id: projectId },
    throwOnError: true,
  });
  return data;
}
