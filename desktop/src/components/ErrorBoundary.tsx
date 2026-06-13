import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("[ErrorBoundary]", error, info.componentStack);
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null });
    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;
      return (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            height: "100vh",
            padding: 24,
            fontFamily: "system-ui, sans-serif",
            color: "#e0e0e0",
            background: "#0f0f1a",
            textAlign: "center",
          }}
        >
          <div style={{ fontSize: 48, marginBottom: 16 }}>⚠</div>
          <h1 style={{ fontSize: 20, fontWeight: 600, margin: "0 0 8px" }}>
            DataBox 启动异常
          </h1>
          <p style={{ fontSize: 14, color: "#888", maxWidth: 480, lineHeight: 1.6 }}>
            应用初始化时发生了未预期的错误。请尝试重启应用。
          </p>
          {this.state.error && (
            <pre
              style={{
                marginTop: 16,
                padding: "8px 16px",
                background: "#1a1a2e",
                borderRadius: 6,
                fontSize: 12,
                color: "#e06060",
                maxWidth: 560,
                overflow: "auto",
                textAlign: "left",
              }}
            >
              {this.state.error.message}
            </pre>
          )}
          <button
            onClick={this.handleReset}
            style={{
              marginTop: 20,
              padding: "8px 24px",
              fontSize: 14,
              borderRadius: 6,
              border: "1px solid #444",
              background: "#1a1a2e",
              color: "#e0e0e0",
              cursor: "pointer",
            }}
          >
            重新加载
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
