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
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;
      return (
        <div className="app-error-boundary">
          <div className="app-error-boundary-icon">⚠</div>
          <h1 className="app-error-boundary-title">
            DBFox 启动异常
          </h1>
          <p className="app-error-boundary-message">
            应用初始化时发生了未预期的错误。请尝试重启应用。
          </p>
          {this.state.error && (
            <pre className="app-error-boundary-detail">
              {this.state.error.message}
            </pre>
          )}
          <button className="app-error-boundary-reset" onClick={this.handleReset}>
            重新加载
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
