import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";

interface Props {
  readonly dlcId?: string;
  readonly componentName?: string;
  readonly children?: ReactNode;
  readonly fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error?: Error;
}

export class DlcErrorBoundary extends Component<Props, State> {
  public override state: State = {
    hasError: false,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public override componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    console.error(
      `[DLC ErrorBoundary] Error in DLC component (${this.props.dlcId ?? "unknown"}:${this.props.componentName ?? "anonymous"}):`,
      error,
      errorInfo,
    );
  }

  private handleRetry = () => {
    this.setState({ hasError: false, error: undefined });
  };

  public override render(): ReactNode {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div
          className="p-4 rounded-lg border border-red-500/20 bg-red-500/5 text-slate-300 flex flex-col gap-2 my-2"
          role="alert"
        >
          <div className="flex items-center gap-2 text-red-400 font-medium text-sm">
            <AlertTriangle className="w-4 h-4 text-red-400 shrink-0" />
            <span>
              扩展组件加载或渲染失败
              {this.props.dlcId ? ` (${this.props.dlcId})` : ""}
            </span>
          </div>
          {this.state.error ? (
            <p className="text-xs text-slate-400 font-mono bg-black/20 p-2 rounded break-all">
              {this.state.error.message || String(this.state.error)}
            </p>
          ) : null}
          <div className="flex items-center gap-2 mt-1">
            <button
              type="button"
              onClick={this.handleRetry}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition-colors"
            >
              <RefreshCw className="w-3 h-3" />
              重试渲染
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
