import type { Plugin } from "unified";

interface CitationPluginOptions {
  artifactOrder: string[];
  allowedArtifactEmbeds?: string[];
}

interface MarkdownNode {
  type: string;
  value?: string;
  url?: string;
  children?: MarkdownNode[];
  data?: {
    hName?: string;
    hProperties?: Record<string, unknown>;
  };
}

const CITATION_PATTERN = /\{\{cite:(artifact_[A-Za-z0-9_-]+)\}\}/g;
const ARTIFACT_EMBED_PATTERN = /^\s*\{\{artifact:(artifact_[A-Za-z0-9_-]+)\}\}\s*$/;

/** Turns DBFox's durable Artifact references into ordinary Markdown link nodes. */
export const remarkDbfoxCitations: Plugin<[CitationPluginOptions]> = (options) => {
  return (tree) => {
    const indexes = new Map(options.artifactOrder.map((id, index) => [id, index + 1]));
    transformChildren(
      tree as MarkdownNode,
      indexes,
      new Set(options.allowedArtifactEmbeds ?? []),
    );
  };
};

function transformChildren(
  node: MarkdownNode,
  indexes: Map<string, number>,
  allowedArtifactEmbeds: Set<string>,
): void {
  if (!node.children) return;
  const nextChildren: MarkdownNode[] = [];
  for (const child of node.children) {
    const embed = paragraphArtifactEmbed(child);
    if (embed && allowedArtifactEmbeds.has(embed)) {
      nextChildren.push({
        type: "dbfoxArtifactEmbed",
        data: {
          hName: "dbfox-artifact-embed",
          hProperties: { dataArtifactId: embed },
        },
      });
      continue;
    }
    if (child.type !== "text" || !child.value?.includes("{{cite:")) {
      transformChildren(child, indexes, allowedArtifactEmbeds);
      nextChildren.push(child);
      continue;
    }

    let offset = 0;
    for (const match of child.value.matchAll(CITATION_PATTERN)) {
      const start = match.index;
      if (start > offset) nextChildren.push({ type: "text", value: child.value.slice(offset, start) });
      const artifactId = match[1];
      if (!indexes.has(artifactId)) indexes.set(artifactId, indexes.size + 1);
      nextChildren.push({
        type: "link",
        url: `#dbfox-artifact:${encodeURIComponent(artifactId)}`,
        children: [{ type: "text", value: String(indexes.get(artifactId)) }],
      });
      offset = start + match[0].length;
    }
    if (offset < child.value.length) nextChildren.push({ type: "text", value: child.value.slice(offset) });
  }
  node.children = nextChildren;
}

function paragraphArtifactEmbed(node: MarkdownNode): string | null {
  if (node.type !== "paragraph" || node.children?.length !== 1) return null;
  const child = node.children[0];
  if (child.type !== "text" || !child.value) return null;
  return child.value.match(ARTIFACT_EMBED_PATTERN)?.[1] ?? null;
}

export function artifactEmbedIds(content: string): string[] {
  return content
    .split(/\r?\n/)
    .flatMap((line) => {
      const match = line.match(ARTIFACT_EMBED_PATTERN);
      return match ? [match[1]] : [];
    });
}
