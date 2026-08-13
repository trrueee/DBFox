import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("[ErrorBoundary]", error, info.componentStack);
  }

  handleReset = () => {
    this.setState({ hasError: false });
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
          <button className="app-error-boundary-reset" onClick={this.handleReset}>
            重新加载
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
