import type { Plugin } from "unified";

interface CitationPluginOptions {
  citations: Array<{ artifact_id: string; locator?: Record<string, unknown> }>;
  allowedArtifactEmbeds?: string[];
  streaming?: boolean;
}

interface MarkdownNode {
  type: string;
  value?: string;
  url?: string;
  children?: MarkdownNode[];
  position?: { start: { offset?: number }; end: { offset?: number } };
  data?: {
    hName?: string;
    hProperties?: Record<string, unknown>;
  };
}

const CITATION_PATTERN = /\{\{cite:(artifact_[A-Za-z0-9_-]+)\}\}/g;
const ARTIFACT_EMBED_PATTERN = /^\s*\{\{artifact:(artifact_[A-Za-z0-9_-]+)\}\}\s*$/;

/** Turns DBFox's durable Artifact references into ordinary Markdown link nodes. */
export const remarkDbfoxCitations: Plugin<[CitationPluginOptions]> = (options) => {
  return (tree, file) => {
    const indexes = new Map<string, number[]>();
    options.citations.forEach((citation, index) => {
      const positions = indexes.get(citation.artifact_id) ?? [];
      positions.push(index);
      indexes.set(citation.artifact_id, positions);
    });
    const seen = new Map<string, number>();
    const sourceCitations = Array.from(String(file).matchAll(CITATION_PATTERN), (match, index) => {
      const occurrence = seen.get(match[1]) ?? 0;
      seen.set(match[1], occurrence + 1);
      return { artifactId: match[1], start: match.index, number: index + 1, occurrence };
    });
    const resolveCitation = (node: MarkdownNode, artifactId: string, localIndex: number): number | undefined => {
      // remark positions refer to the original UTF-16 source. Counting original
      // markers also includes code examples, so those cannot shift a later link
      // onto the wrong claim. Python answer offsets are deliberately not reused.
      const start = node.position?.start.offset;
      const end = node.position?.end.offset;
      if (start === undefined || end === undefined) return undefined;
      const source = sourceCitations.filter(item => item.start >= start && item.start < end)[localIndex];
      if (!source || source.artifactId !== artifactId) return undefined;
      const positions = indexes.get(artifactId);
      if (!positions) return undefined;
      const numbered = positions.filter(index => citationNumber(options.citations[index]) !== undefined);
      return numbered.length
        ? numbered.find(index => citationNumber(options.citations[index]) === source.number)
        : positions[Math.min(source.occurrence, positions.length - 1)];
    };
    transformChildren(
      tree as MarkdownNode,
      new Set(options.allowedArtifactEmbeds ?? []),
      options.streaming ?? false,
      resolveCitation,
    );
  };
};

function transformChildren(
  node: MarkdownNode,
  allowedArtifactEmbeds: Set<string>,
  streaming: boolean,
  resolveCitation: (node: MarkdownNode, artifactId: string, localIndex: number) => number | undefined,
): void {
  if (!node.children) return;
  const nextChildren: MarkdownNode[] = [];
  for (const child of node.children) {
    if (streaming && child.type === "text") {
      child.value = child.value?.replace(/\{\{(?:cite|artifact):[^}]*$/, "");
    }
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
      if (child.type !== "code" && child.type !== "inlineCode" && child.type !== "link") {
        transformChildren(child, allowedArtifactEmbeds, streaming, resolveCitation);
      }
      nextChildren.push(child);
      continue;
    }

    let offset = 0;
    let localIndex = 0;
    for (const match of child.value.matchAll(CITATION_PATTERN)) {
      const start = match.index;
      if (start > offset) nextChildren.push({ type: "text", value: child.value.slice(offset, start) });
      const artifactId = match[1];
      const index = resolveCitation(child, artifactId, localIndex++);
      nextChildren.push(index === undefined ? { type: "text", value: "〔来源待确认〕" } : {
        type: "link",
        url: `#dbfox-citation:${index}`,
        children: [{ type: "text", value: String(index + 1) }],
      });
      offset = start + match[0].length;
    }
    if (offset < child.value.length) nextChildren.push({ type: "text", value: child.value.slice(offset) });
  }
  node.children = nextChildren;
}

function citationNumber(citation: CitationPluginOptions["citations"][number]): number | undefined {
  const value = citation.locator?.value;
  if (value && typeof value === "object" && "citation_index" in value && typeof value.citation_index === "number") {
    return value.citation_index;
  }
  return undefined;
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
