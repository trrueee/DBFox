type MarkdownNode = {
  type?: string;
  value?: string;
  children?: MarkdownNode[];
};

const SAFE_BREAK = /^<br\s*\/?\s*>$/i;

/** Preserve the one presentational HTML token we support without parsing raw HTML. */
export function remarkSafeBreaks() {
  return (tree: MarkdownNode) => transformChildren(tree);
}

function transformChildren(node: MarkdownNode): void {
  if (!Array.isArray(node.children)) return;
  node.children = node.children.map((child) => {
    if (child.type === "html" && SAFE_BREAK.test(child.value || "")) {
      return { type: "break" };
    }
    transformChildren(child);
    return child;
  });
}
