import { Component, type ErrorInfo, type ReactNode } from "react";
import { RotateCcw, TriangleAlert } from "lucide-react";
import {
  Button,
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "./ui";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
}

export function FatalErrorFallback({ onRetry }: { onRetry: () => void }) {
  return (
    <Empty className="app-error-boundary-panel" role="alert">
      <EmptyHeader>
        <EmptyMedia variant="icon">
          <TriangleAlert aria-hidden="true" />
        </EmptyMedia>
        <EmptyTitle role="heading" aria-level={1}>DBFox 界面发生异常</EmptyTitle>
        <EmptyDescription>
          当前界面无法继续渲染。可以先重试；如果问题持续出现，请重启应用并查看诊断日志。
        </EmptyDescription>
      </EmptyHeader>
      <EmptyContent>
        <Button type="button" onClick={onRetry}>
          <RotateCcw size={14} aria-hidden="true" />
          重试渲染
        </Button>
      </EmptyContent>
    </Empty>
  );
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
        <main className="app-error-boundary">
          <FatalErrorFallback onRetry={this.handleReset} />
        </main>
      );
    }
    return this.props.children;
  }
}
