import { useEffect, useRef, useState } from "react";
import { FileText } from "lucide-react";
import { defaultKeymap, history, historyKeymap } from "@codemirror/commands";
import { bracketMatching, indentOnInput, syntaxHighlighting } from "@codemirror/language";
import { highlightSelectionMatches, searchKeymap } from "@codemirror/search";
import { EditorState } from "@codemirror/state";
import {
  drawSelection,
  dropCursor,
  EditorView,
  highlightActiveLine,
  highlightActiveLineGutter,
  highlightSpecialChars,
  keymap,
  lineNumbers,
  rectangularSelection,
} from "@codemirror/view";
import { classHighlighter } from "@lezer/highlight";

import { WorkspaceShell } from "../appShell/WorkspaceShell";
import { readProjectFile, type ProjectFileContent } from "../../lib/projectFolder";
import type { WorkspaceDockTab } from "../../types/workspace";
import "./WorkspaceFileDock.css";

function formatFileSize(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KiB`;
  return `${(size / 1024 / 1024).toFixed(1)} MiB`;
}

function ReadOnlyCodeEditor({ value }: { value: string }) {
  const hostRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef<EditorView | null>(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return undefined;

    const view = new EditorView({
      parent: host,
      state: EditorState.create({
        doc: value,
        extensions: [
          EditorState.readOnly.of(true),
          EditorView.editable.of(false),
          lineNumbers(),
          highlightActiveLineGutter(),
          highlightSpecialChars(),
          history(),
          drawSelection(),
          dropCursor(),
          rectangularSelection(),
          highlightActiveLine(),
          highlightSelectionMatches(),
          bracketMatching(),
          indentOnInput(),
          syntaxHighlighting(classHighlighter),
          keymap.of([
            ...defaultKeymap,
            ...searchKeymap,
            ...historyKeymap,
          ]),
          EditorView.lineWrapping,
          EditorView.contentAttributes.of({
            "aria-label": "项目文件内容",
            "aria-readonly": "true",
            spellcheck: "false",
          }),
          EditorView.theme({
            "&": { height: "100%" },
            ".cm-scroller": { overflow: "auto" },
            ".cm-content": { minHeight: "100%" },
          }),
        ],
      }),
    });
    viewRef.current = view;

    return () => {
      viewRef.current = null;
      view.destroy();
    };
  }, [value]);

  return <div ref={hostRef} className="workspace-file-dock__editor" data-testid="workspace-file-editor" />;
}

export function WorkspaceFileDockContent({ tab }: { tab: WorkspaceDockTab }) {
  const filePath = tab.filePath ?? "";
  const [result, setResult] = useState<ProjectFileContent | null>(null);
  const [loading, setLoading] = useState(Boolean(filePath));
  const [reloadSeq, setReloadSeq] = useState(0);

  useEffect(() => {
    if (!filePath) return;
    let cancelled = false;
    void readProjectFile(filePath)
      .then((content) => {
        if (!cancelled) setResult(content);
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setResult({
            path: filePath,
            name: tab.fileName ?? filePath,
            content: null,
            binary: false,
            size: 0,
            error: error instanceof Error ? error.message : "读取文件失败",
          });
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [filePath, reloadSeq, tab.fileName]);

  const title = tab.fileName ?? filePath;
  const retry = () => {
    setResult(null);
    setLoading(true);
    setReloadSeq((value) => value + 1);
  };
  const state = !filePath
    ? { kind: "error" as const, title: "无法预览文件", description: "文件路径为空", retryLabel: undefined }
    : loading
      ? { kind: "loading" as const, label: "正在读取文件…" }
      : result?.content != null
        ? { kind: "ready" as const }
        : { kind: "error" as const, title: "无法预览文件", description: result?.error ?? "文件内容为空或不可读", onRetry: retry, retryLabel: "重新读取" };

  return (
    <WorkspaceShell
      title={title}
      description={filePath}
      state={state}
      bodyClassName="workspace-shell__body--workspace-file"
      className="workspace-file-dock"
    >
      {result?.content != null ? (
        <>
          <div className="workspace-file-dock__meta">
            <FileText size={13} aria-hidden="true" />
            <span>{formatFileSize(result.size)}</span>
            <span>只读 · UTF-8</span>
          </div>
          <ReadOnlyCodeEditor value={result.content} />
        </>
      ) : null}
    </WorkspaceShell>
  );
}
