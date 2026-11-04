import { useEffect, useState, type ReactNode } from "react";
import { AtSign } from "lucide-react";
import { highlightCode, classHighlighter } from "@lezer/highlight";
import { LanguageDescription } from "@codemirror/language";
import { Button } from "../ui";
import { MarkdownContent } from "../../features/workspace/queryResult/MarkdownContent";
import { fileKind, ResourceIcon } from "./resourcePresentation";
import "./file-content.css";

type ViewMode = "preview" | "source" | "split";

function CodeContent({ name, content }: { name: string; content: string }) {
  const [highlighted, setHighlighted] = useState<{ name: string; content: string; lines: ReactNode[][] }>();
  useEffect(() => {
    let active = true;
    void import("@codemirror/language-data").then(async ({ languages }) => {
      const language = LanguageDescription.matchFilename(languages, name);
      if (!language) return;
      const support = await language.load();
      if (!active) return;
      const lines: ReactNode[][] = [[]];
      let token = 0;
      highlightCode(content, support.language.parser.parse(content), classHighlighter,
        (text, classes) => { lines.at(-1)!.push(<span key={token++} className={classes || undefined}>{text}</span>); },
        () => { lines.push([]); });
      if (active) setHighlighted({ name, content, lines });
    }).catch(() => { /* The source remains readable when a language chunk cannot load. */ });
    return () => { active = false; };
  }, [name, content]);
  const lines = highlighted?.name === name && highlighted.content === content
    ? highlighted.lines : content.split("\n").map(line => [line]);
  return <div className="file-code" role="region" aria-label={`${name} 源码`}>
    {lines.slice(0, 10_000).map((line, index) => <div className="file-code__line" key={index}>
      <span className="file-code__number" aria-hidden="true">{index + 1}</span><code>{line.length ? line : " "}</code>
    </div>)}
    {lines.length > 10_000 ? <p className="file-content__notice">当前显示前 10,000 行。</p> : null}
  </div>;
}

/** Shared read-only file surface. The owning DLC supplies the authorized bytes. */
export function FileContent({ name, content, onAsk }: { name: string; content: string; onAsk?: () => void }) {
  const markdown = fileKind(name) === "markdown";
  const [mode, setMode] = useState<ViewMode>("preview");
  const showSource = !markdown || mode !== "preview";
  const showPreview = markdown && mode !== "source";
  return <section className="file-content" aria-label={name}>
    <header className="file-content__header"><span className="file-content__identity"><ResourceIcon name={name} size={16} /><span title={name}>{name.split(/[\\/]/).join(" › ")}</span></span>
      <div className="file-content__tools">
        {markdown ? <div className="file-content__modes" role="group" aria-label="Markdown 查看方式">{(["preview", "source", "split"] as const).map(value => <Button key={value} type="button" variant="ghost" size="sm" aria-pressed={mode === value} onClick={() => setMode(value)}>{({ preview: "预览", source: "源码", split: "分栏" })[value]}</Button>)}</div> : <span className="file-content__format">{name.split(".").at(-1)?.toUpperCase() || "文本"}</span>}
        {onAsk ? <Button type="button" variant="ghost" size="sm" onClick={onAsk}><AtSign size={14} aria-hidden="true" />加入对话</Button> : null}
      </div></header>
    <div className={`file-content__body${markdown && mode === "split" ? " file-content__body--split" : ""}`}>
      {showSource ? <CodeContent name={name} content={content} /> : null}
      {showPreview ? <div className="file-content__markdown"><MarkdownContent content={content} /></div> : null}
    </div>
    <footer className="file-content__footer"><span>{markdown ? "Markdown" : "UTF-8"}</span><span>只读</span></footer>
  </section>;
}
