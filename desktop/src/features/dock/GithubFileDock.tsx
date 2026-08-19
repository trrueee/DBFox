import { useEffect, useRef, useState } from "react";
import { GitBranch, FileText } from "lucide-react";
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
import { githubApi } from "../../lib/api/github";
import { useGithubStore } from "../github/githubStore";
import type { WorkspaceDockTab } from "../../types/workspace";
import type { GithubFileContentResponse } from "../../lib/api/generated/types.gen";
import "../workspace/WorkspaceFileDock.css";

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
            "aria-label": "GitHub 文件内容",
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

  return <div ref={hostRef} className="workspace-file-dock__editor" data-testid="github-file-editor" />;
}

export function GithubFileDockContent({ tab }: { tab: WorkspaceDockTab }) {
  const fileState = useGithubStore((s) => s.fileStateByKey[tab.stateKey ?? tab.viewKey]);
  const projectId = fileState?.projectId ?? tab.projectId ?? "";
  const bindingId = fileState?.bindingId ?? "";
  const filePath = fileState?.filePath ?? "";
  const fileName = fileState?.fileName ?? tab.title;
  const owner = fileState?.owner ?? "";
  const repository = fileState?.repository ?? "";
  const revision = fileState?.revision ?? "";

  const [data, setData] = useState<GithubFileContentResponse | null>(null);
  const [loading, setLoading] = useState(Boolean(projectId && bindingId && filePath));
  const [error, setError] = useState<string | null>(null);
  const [reloadSeq, setReloadSeq] = useState(0);

  useEffect(() => {
    if (!projectId || !bindingId || !filePath) return;
    let cancelled = false;

    void githubApi
      .readFile(projectId, bindingId, filePath)
      .then((res) => {
        if (!cancelled) {
          setData(res);
          setError(null);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "读取 GitHub 文件失败");
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [projectId, bindingId, filePath, reloadSeq]);

  const title = fileName || filePath;
  const retry = () => {
    setData(null);
    setLoading(true);
    setReloadSeq((v) => v + 1);
  };

  const state = !filePath
    ? { kind: "error" as const, title: "无法预览文件", description: "文件路径为空", retryLabel: undefined }
    : loading
      ? { kind: "loading" as const, label: "正在从 GitHub 读取文件…" }
      : data?.content != null
        ? { kind: "ready" as const }
        : {
            kind: "error" as const,
            title: "无法预览文件",
            description: error ?? "文件内容为空或不可读",
            onRetry: retry,
            retryLabel: "重新读取",
          };

  const description = owner && repository
    ? `${owner}/${repository} @ ${revision ? revision.slice(0, 7) : "HEAD"} — ${filePath}`
    : filePath;

  return (
    <WorkspaceShell
      title={title}
      description={description}
      state={state}
      bodyClassName="workspace-shell__body--workspace-file"
      className="workspace-file-dock"
    >
      {data?.content != null ? (
        <>
          <div className="workspace-file-dock__meta">
            <GitBranch size={13} aria-hidden="true" />
            <span>{owner}/{repository}</span>
            <FileText size={13} aria-hidden="true" />
            <span>{formatFileSize(data.size_bytes)}</span>
            <span>只读 · UTF-8</span>
            {data.truncated ? (
              <span className="badge badge--warning">
                已截断至前 {formatFileSize(data.content.length)}
              </span>
            ) : null}
          </div>
          <ReadOnlyCodeEditor value={data.content} />
        </>
      ) : null}
    </WorkspaceShell>
  );
}
