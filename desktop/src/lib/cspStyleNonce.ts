/**
 * The empty style anchor in index.html makes Tauri emit a fresh style nonce
 * and add it to the packaged CSP. Monaco creates style elements at runtime,
 * but does not propagate that nonce itself. Patch only the current document's
 * style-element factory so trusted framework-generated styles retain the host
 * nonce before insertion.
 */
const originalCreateElement = new WeakMap<Document, Document["createElement"]>();

function currentStyleCspNonce(documentRef: Document): string | null {
  return documentRef.querySelector<HTMLStyleElement>("style[data-tauri-csp-style-nonce][nonce]")?.nonce || null;
}

export function installCspStyleNoncePropagation(documentRef: Document = document): () => void {
  const nonce = currentStyleCspNonce(documentRef);
  if (!nonce || originalCreateElement.has(documentRef)) return () => {};

  const createElement = documentRef.createElement;
  const patchedCreateElement = ((tagName: string, options?: ElementCreationOptions) => {
    const element = Reflect.apply(createElement, documentRef, [tagName, options]) as Element;
    if (tagName.toLowerCase() === "style" && "nonce" in element) {
      (element as HTMLStyleElement).nonce = nonce;
    }
    return element;
  }) as Document["createElement"];

  originalCreateElement.set(documentRef, createElement);
  documentRef.createElement = patchedCreateElement;

  return () => {
    if (documentRef.createElement === patchedCreateElement) {
      documentRef.createElement = createElement;
    }
    originalCreateElement.delete(documentRef);
  };
}
