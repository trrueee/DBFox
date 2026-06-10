import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";
import { ShieldAlert } from "lucide-react";
import { Button } from "@/components/ui/button";

interface Props { children: ReactNode; fallback?: ReactNode; title?: string; }
interface State { hasError: boolean; error: Error | null; }

export class ErrorBoundary extends Component<Props, State> {
  public state: State = { hasError: false, error: null };

  public static getDerivedStateFromError(error: Error): State { return { hasError: true, error }; }
  public componentDidCatch(error: Error, errorInfo: ErrorInfo) { console.error("ErrorBoundary:", error, errorInfo); }

  public render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;
      return (
        <div className="p-5 border border-[hsl(var(--destructive))] bg-[hsl(var(--destructive)/0.03)] rounded-lg flex flex-col gap-3 items-start m-2">
          <div className="flex items-center gap-2 text-[hsl(var(--destructive))]">
            <ShieldAlert size={18} />
            <strong className="text-sm">{this.props.title || "局部模块渲染异常"}</strong>
          </div>
          <p className="text-xs text-[hsl(var(--muted-foreground))] leading-relaxed">组件内部发生未捕获解析错误。可能是由于异常大字段、数据解析失败或格式不兼容所致。</p>
          <pre className="w-full max-h-[100px] overflow-auto bg-[hsl(var(--secondary))] border rounded p-2 text-[0.7rem] font-mono text-[hsl(var(--muted-foreground))] whitespace-pre-wrap break-all">{this.state.error?.stack || this.state.error?.message}</pre>
          <Button variant="outline" size="sm" onClick={() => this.setState({ hasError: false, error: null })}>尝试重新加载</Button>
        </div>
      );
    }
    return this.props.children;
  }
}
