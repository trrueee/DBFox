import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";
import { ShieldAlert } from "lucide-react";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
  title?: string;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("ErrorBoundary caught an error:", error, errorInfo);
  }

  public render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div
          className="lab-card animate-fade-in"
          style={{
            padding: "20px 24px",
            border: "1px solid var(--accent-red)",
            background: "rgba(220, 38, 38, 0.03)",
            borderRadius: 8,
            display: "flex",
            flexDirection: "column",
            gap: 12,
            alignItems: "flex-start",
            margin: "8px 0",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 8, color: "var(--accent-red)" }}>
            <ShieldAlert size={18} />
            <strong style={{ fontSize: "0.88rem" }}>{this.props.title || "局部模块渲染异常"}</strong>
          </div>
          <p style={{ fontSize: "0.8rem", color: "var(--text-secondary)", margin: 0, lineHeight: 1.5 }}>
            组件内部发生未捕获解析错误。可能是由于异常大字段、数据解析失败或格式不兼容所致。
          </p>
          <div
            style={{
              width: "100%",
              overflow: "auto",
              maxHeight: "100px",
              background: "var(--bg-secondary)",
              border: "1px solid var(--border-light)",
              borderRadius: 4,
              padding: 8,
            }}
          >
            <pre
              style={{
                margin: 0,
                fontSize: "0.72rem",
                fontFamily: "var(--font-mono)",
                color: "var(--text-muted)",
                whiteSpace: "pre-wrap",
                wordBreak: "break-all",
              }}
            >
              {this.state.error?.stack || this.state.error?.message}
            </pre>
          </div>
          <button
            className="btn-secondary"
            style={{ padding: "4px 10px", fontSize: "0.74rem" }}
            onClick={() => this.setState({ hasError: false, error: null })}
          >
            尝试重新加载 🔄
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
