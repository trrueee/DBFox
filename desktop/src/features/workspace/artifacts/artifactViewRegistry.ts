import type {
  ArtifactEnvelope,
  ArtifactRepresentationDescriptor,
  ArtifactViewContribution,
  ArtifactViewSurface,
} from "./types";
import { coreArtifactViews } from "./coreArtifactViews";
import { hostArtifactViews } from "./hostArtifactViews";

export interface ArtifactViewRegistry {
  get(id: string): ArtifactViewContribution<unknown> | null;
  all(): readonly ArtifactViewContribution<unknown>[];
}

export function createArtifactViewRegistry(
  contributions: readonly ArtifactViewContribution<unknown>[],
): ArtifactViewRegistry {
  const byId = new Map<string, ArtifactViewContribution<unknown>>();
  for (const contribution of contributions) {
    if (byId.has(contribution.id)) {
      throw new Error(
        `Duplicate Artifact View id "${contribution.id}". Registration must fail closed.`,
      );
    }
    byId.set(contribution.id, contribution);
  }
  return {
    get: (id) => byId.get(id) ?? null,
    all: () => contributions,
  };
}

export function productArtifactViews(): readonly ArtifactViewContribution<unknown>[] {
  return [
    ...coreArtifactViews,
    ...hostArtifactViews,
  ];
}

export function matchingArtifactViews(
  artifact: ArtifactEnvelope<unknown>,
  representations: readonly ArtifactRepresentationDescriptor[],
  surface: ArtifactViewSurface,
  contributions: readonly ArtifactViewContribution<unknown>[],
): ArtifactViewContribution<unknown>[] {
  const representationTypes = new Set(
    representations.map((descriptor) => descriptor.representation_type),
  );
  return contributions
    .filter((view) => view.surfaces.includes(surface))
    .filter((view) => {
      const artifactMatch = !view.artifactTypes?.length || view.artifactTypes.some((selector) => (
        selector.type === artifact.type
        && (!selector.schemaVersions?.length
          || selector.schemaVersions.includes(artifact.schema_version ?? 1))
      ));
      const representationMatch = !view.representationTypes?.length
        || view.representationTypes.every((type) => representationTypes.has(type));
      return artifactMatch && representationMatch;
    })
    .sort((left, right) => (
      (right.priority ?? 0) - (left.priority ?? 0)
      || left.title.localeCompare(right.title)
      || left.id.localeCompare(right.id)
    ));
}
