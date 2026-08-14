import { useEffect, useMemo, useRef } from "react";
import {
  autocompletion,
  closeBrackets,
  closeBracketsKeymap,
  completionKeymap,
} from "@codemirror/autocomplete";
import { defaultKeymap, history, historyKeymap, indentWithTab } from "@codemirror/commands";
import { bracketMatching, foldGutter, indentOnInput, syntaxHighlighting } from "@codemirror/language";
import { highlightSelectionMatches, searchKeymap } from "@codemirror/search";
import { Compartment, EditorState, Prec } from "@codemirror/state";
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

import type { DataSource } from "../../../lib/api/types";
import type { EngineColumn, EngineSchemaTable } from "../../../lib/api/schema";
import { buildSqlLanguage, createQualifiedColumnSource } from "./sqlCompletion";

interface SqlEditorProps {
  value: string;
  disabled: boolean;
  dbType: DataSource["db_type"] | null;
  tables: EngineSchemaTable[];
  loadColumns: (tableId: string) => Promise<EngineColumn[]>;
  onChange: (value: string) => void;
  onSelectionChange: (value: string) => void;
  onExecute: (selectedSql: string) => void;
}

export function SqlEditor({
  value,
  disabled,
  dbType,
  tables,
  loadColumns,
  onChange,
  onSelectionChange,
  onExecute,
}: SqlEditorProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef<EditorView | null>(null);
  const callbacksRef = useRef({ onChange, onSelectionChange, onExecute });
  const languageCompartment = useMemo(() => new Compartment(), []);
  const completionCompartment = useMemo(() => new Compartment(), []);
  const editableCompartment = useMemo(() => new Compartment(), []);

  const language = useMemo(() => buildSqlLanguage(dbType, tables), [dbType, tables]);
  const qualifiedColumnSource = useMemo(
    () => createQualifiedColumnSource(tables, loadColumns),
    [loadColumns, tables],
  );

  useEffect(() => {
    callbacksRef.current = { onChange, onSelectionChange, onExecute };
  }, [onChange, onExecute, onSelectionChange]);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return undefined;

    const executeSelection = (view: EditorView) => {
      const selection = view.state.selection.main;
      const selectedSql = selection.empty
        ? ""
        : view.state.sliceDoc(selection.from, selection.to);
      callbacksRef.current.onSelectionChange(selectedSql);
      callbacksRef.current.onExecute(selectedSql);
      return true;
    };

    const view = new EditorView({
      parent: host,
      state: EditorState.create({
        doc: value,
        extensions: [
          lineNumbers(),
          highlightActiveLineGutter(),
          highlightSpecialChars(),
          history(),
          foldGutter(),
          drawSelection(),
          dropCursor(),
          EditorState.allowMultipleSelections.of(true),
          indentOnInput(),
          bracketMatching(),
          closeBrackets(),
          rectangularSelection(),
          highlightActiveLine(),
          highlightSelectionMatches(),
          syntaxHighlighting(classHighlighter),
          autocompletion({ activateOnTyping: true }),
          languageCompartment.of(language),
          completionCompartment.of(
            EditorState.languageData.of(() => [{ autocomplete: qualifiedColumnSource }]),
          ),
          editableCompartment.of(EditorView.editable.of(!disabled)),
          EditorView.contentAttributes.of({
            "aria-label": "SQL 编辑器",
            "aria-readonly": disabled ? "true" : "false",
            spellcheck: "false",
          }),
          Prec.high(
            keymap.of([
              { key: "F9", run: executeSelection },
              { key: "Mod-Enter", run: executeSelection },
            ]),
          ),
          keymap.of([
            ...closeBracketsKeymap,
            ...defaultKeymap,
            ...searchKeymap,
            ...historyKeymap,
            ...completionKeymap,
            indentWithTab,
          ]),
          EditorView.updateListener.of((update) => {
            if (update.docChanged) callbacksRef.current.onChange(update.state.doc.toString());
            if (update.selectionSet || update.docChanged) {
              const selection = update.state.selection.main;
              callbacksRef.current.onSelectionChange(
                selection.empty ? "" : update.state.sliceDoc(selection.from, selection.to),
              );
            }
          }),
          EditorView.theme({
            "&": { height: "100%" },
            ".cm-scroller": { overflow: "auto" },
            ".cm-content": { minHeight: "132px" },
          }),
        ],
      }),
    });
    viewRef.current = view;
    view.focus();

    return () => {
      viewRef.current = null;
      view.destroy();
    };
    // The editor lifecycle is tied to the host. Runtime configuration is updated
    // through CodeMirror compartments below without destroying history/selection.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const view = viewRef.current;
    if (!view || view.state.doc.toString() === value) return;
    view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: value } });
  }, [value]);

  useEffect(() => {
    viewRef.current?.dispatch({ effects: languageCompartment.reconfigure(language) });
  }, [language, languageCompartment]);

  useEffect(() => {
    viewRef.current?.dispatch({
      effects: completionCompartment.reconfigure(
        EditorState.languageData.of(() => [{ autocomplete: qualifiedColumnSource }]),
      ),
    });
  }, [completionCompartment, qualifiedColumnSource]);

  useEffect(() => {
    const view = viewRef.current;
    if (!view) return;
    view.dispatch({ effects: editableCompartment.reconfigure(EditorView.editable.of(!disabled)) });
    view.contentDOM.setAttribute("aria-readonly", disabled ? "true" : "false");
  }, [disabled, editableCompartment]);

  return <div ref={hostRef} className="sql-console-editor" data-testid="sql-editor" />;
}
