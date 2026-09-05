import { basicSetup, EditorView, EditorState, Compartment, keymap, indentWithTab, StreamLanguage, shader, setDiagnostics, HighlightStyle, syntaxHighlighting, tags } from './vendor/codemirror.js';

export function mountEditor(parent, { source, onChange, onSelection, onSave, readOnly = false }) {
  const root = parent.shadowRoot ?? parent.attachShadow({ mode: 'open' });
  const editable = new Compartment();
  let replacing = false;
  const view = new EditorView({
    parent: root, root,
    state: EditorState.create({ doc: source, extensions: [
      basicSetup, StreamLanguage.define(shader),
      syntaxHighlighting(HighlightStyle.define([
        { tag: [tags.keyword, tags.operatorKeyword, tags.function(tags.variableName)], color: 'var(--color-primary)' },
        { tag: [tags.typeName, tags.string], color: 'var(--color-success)' },
        { tag: [tags.number, tags.atom, tags.bool], color: 'var(--color-warning)' },
        { tag: [tags.variableName, tags.propertyName, tags.punctuation], color: 'var(--color-text-primary)' },
        { tag: tags.comment, color: 'var(--color-text-muted)' },
        { tag: tags.meta, color: 'var(--color-text-secondary)' },
        { tag: tags.invalid, color: 'var(--color-danger)' },
      ])),
      editable.of([EditorState.readOnly.of(readOnly), EditorView.editable.of(!readOnly)]),
      EditorView.contentAttributes.of({ 'aria-label': 'GLSL source editor', 'aria-description': 'GLSL ES 3.00. Control or Command S saves. Tab indents.' }),
      keymap.of([{ key: 'Mod-s', run: () => { onSave?.(); return true; } }, indentWithTab]),
      EditorView.updateListener.of((update) => {
        if (update.docChanged && !replacing) onChange(update.state.doc.toString());
        if (update.selectionSet || update.docChanged) {
          const selection = update.state.selection.main;
          onSelection?.({ from: update.state.doc.lineAt(selection.from).number, to: update.state.doc.lineAt(selection.to).number });
        }
      }),
      EditorView.theme({
        '&': { height: '100%', color: 'var(--color-text-primary)', backgroundColor: 'var(--surface-canvas)' },
        '.cm-scroller': { overflow: 'auto', fontFamily: 'var(--font-mono)', fontSize: 'var(--ui-font-code)', lineHeight: 'var(--code-line-height)' },
        '.cm-content': { padding: '12px 0', caretColor: 'var(--color-primary)' },
        '.cm-gutters': { backgroundColor: 'var(--surface-canvas)', color: 'var(--color-text-muted)', borderRight: '1px solid var(--color-border)' },
        '.cm-activeLine, .cm-activeLineGutter': { backgroundColor: 'var(--color-primary-soft)' },
        '&.cm-focused': { outline: '2px solid var(--color-primary)', outlineOffset: '-2px' },
        '.cm-tooltip': { backgroundColor: 'var(--surface-overlay)', color: 'var(--color-text-primary)', border: '1px solid var(--color-border)' },
        '.cm-selectionBackground, &.cm-focused .cm-selectionBackground': { backgroundColor: 'var(--color-primary-soft)' },
        '.cm-panels': { backgroundColor: 'var(--surface-panel)', color: 'var(--color-text-primary)' },
      }),
    ] }),
  });
  return {
    replace(text) {
      if (view.state.doc.toString() === text) return;
      replacing = true;
      try { view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: text } }); }
      finally { replacing = false; }
    },
    setReadOnly(value) { view.dispatch({ effects: editable.reconfigure([EditorState.readOnly.of(value), EditorView.editable.of(!value)]) }); },
    diagnostics(items) {
      view.dispatch(setDiagnostics(view.state, items.filter((item) => item.line).map((item) => {
        const line = view.state.doc.line(Math.max(1, Math.min(view.state.doc.lines, item.line)));
        return { from: line.from, to: line.to, severity: item.severity, message: `${item.code}: ${item.message}` };
      })));
    },
    focusLine(number) {
      const line = view.state.doc.line(Math.max(1, Math.min(view.state.doc.lines, number)));
      view.dispatch({ selection: { anchor: line.from }, effects: EditorView.scrollIntoView(line.from, { y: 'center' }) }); view.focus();
    },
    destroy() { view.destroy(); root.replaceChildren(); },
  };
}
