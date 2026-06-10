import { Copy, Play, FileCode, MessageSquare } from "lucide-react";
import { Button } from "../../components/ui/button";
import { Badge } from "../../components/ui/badge";

interface SQLCardProps {
  sql: string;
  title?: string;
  isProd?: boolean;
  onCopy?: () => void;
  onInsert?: () => void;
  onRun?: () => void;
  onExplain?: () => void;
}

export function SQLCard({
  sql,
  title = "SQL 查询建议",
  isProd = false,
  onCopy,
  onInsert,
  onRun,
  onExplain,
}: SQLCardProps) {
  const handleCopy = () => {
    navigator.clipboard.writeText(sql).catch(() => {});
    onCopy?.();
  };

  return (
    <div className="rounded border border-[hsl(var(--border))] bg-[hsl(var(--card))] overflow-hidden border-l-2 border-l-[hsl(var(--primary))]">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-1.5 bg-[hsl(var(--secondary))] border-b border-[hsl(var(--border))]">
        <span className="flex items-center gap-1.5 text-[0.7rem] font-semibold text-[hsl(var(--muted-foreground))]">
          <FileCode size={13} className="text-[hsl(var(--primary))]" />
          {title}
        </span>
        {isProd && (
          <Badge variant="destructive" className="text-[0.6rem] px-1.5 py-0">
            PROD
          </Badge>
        )}
      </div>

      {/* SQL Body */}
      <pre className="px-3 py-2 m-0 font-mono text-[0.72rem] leading-relaxed text-[hsl(var(--foreground))] whitespace-pre-wrap break-all overflow-x-auto max-h-[200px] overflow-y-auto">
        <code>{sql}</code>
      </pre>

      {/* Actions */}
      <div className="flex gap-1.5 px-2 py-1.5 border-t border-[hsl(var(--border))] bg-[hsl(var(--background))] flex-wrap">
        <Button
          variant="outline"
          size="sm"
          onClick={handleCopy}
          title="复制 SQL"
          className="h-7 text-[0.65rem] gap-1"
        >
          <Copy size={11} />
          复制
        </Button>
        {onInsert && (
          <Button
            variant="outline"
            size="sm"
            onClick={onInsert}
            title="插入到编辑器"
            className="h-7 text-[0.65rem] gap-1 border-[hsl(var(--primary))] text-[hsl(var(--primary))]"
          >
            <FileCode size={11} />
            插入编辑器
          </Button>
        )}
        {onRun && (
          <Button
            size="sm"
            onClick={onRun}
            title={isProd ? "在生产环境执行" : "运行查询"}
            className="h-7 text-[0.65rem] gap-1"
          >
            <Play size={11} />
            运行
          </Button>
        )}
        {onExplain && (
          <Button
            variant="outline"
            size="sm"
            onClick={onExplain}
            title="解释这条 SQL"
            className="h-7 text-[0.65rem] gap-1"
          >
            <MessageSquare size={11} />
            解释
          </Button>
        )}
      </div>

      {isProd && onRun && (
        <div className="px-3 py-1 text-[0.6rem] text-[hsl(var(--muted-foreground))] bg-[hsl(var(--secondary))] border-t border-[hsl(var(--border))]">
          生产环境 · 用户手动执行 SELECT 语句无需额外审批
        </div>
      )}
    </div>
  );
}
