import type { Plugin } from "unified";

interface CitationPluginOptions {
  artifactOrder: string[];
}

interface MarkdownNode {
  type: string;
  value?: string;
  url?: string;
  children?: MarkdownNode[];
}

const CITATION_PATTERN = /\{\{cite:(artifact_[A-Za-z0-9_-]+)\}\}/g;

/** Turns DBFox's durable Artifact references into ordinary Markdown link nodes. */
export const remarkDbfoxCitations: Plugin<[CitationPluginOptions]> = (options) => {
  return (tree) => {
    const indexes = new Map(options.artifactOrder.map((id, index) => [id, index + 1]));
    transformChildren(tree as MarkdownNode, indexes);
  };
};

function transformChildren(node: MarkdownNode, indexes: Map<string, number>): void {
  if (!node.children) return;
  const nextChildren: MarkdownNode[] = [];
  for (const child of node.children) {
    if (child.type !== "text" || !child.value?.includes("{{cite:")) {
      transformChildren(child, indexes);
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
