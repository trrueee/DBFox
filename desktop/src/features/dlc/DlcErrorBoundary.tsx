import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";
import { Alert, AlertDescription, AlertTitle, Button } from "../../components/ui";
import "./DlcErrorBoundary.css";

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
        <Alert className="dlc-error-state" variant="destructive">
          <AlertTriangle aria-hidden="true" />
          <AlertTitle>
            扩展组件加载或渲染失败
            {this.props.dlcId ? ` (${this.props.dlcId})` : ""}
          </AlertTitle>
          <AlertDescription>
            <p>这个扩展的界面暂时不可用。可重试渲染；详细原因只记录在诊断日志中。</p>
            <Button type="button" variant="outline" size="sm" onClick={this.handleRetry}>
              <RefreshCw size={14} aria-hidden="true" />
              重试渲染
            </Button>
          </AlertDescription>
        </Alert>
      );
    }

    return this.props.children;
  }
}
