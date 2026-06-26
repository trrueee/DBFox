import { useId, type HTMLAttributes, type ReactNode } from "react";
import { EmptyState, ErrorState, LoadingState } from "../../components/ui";
import "./WorkspaceShell.css";

type WorkspaceShellState =
  | { kind?: "ready" }
  | { kind: "loading"; label?: string }
  | { kind: "empty"; title: string; description?: string; action?: ReactNode }
  | { kind: "error"; title: string; description?: string; onRetry?: () => void; retryLabel?: string };

interface WorkspaceShellProps extends Omit<HTMLAttributes<HTMLDivElement>, "title"> {
  title: ReactNode;
  description?: ReactNode;
  toolbar?: ReactNode;
  state?: WorkspaceShellState;
  bodyClassName?: string;
}

function cx(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

export function WorkspaceShell({
  title,
  description,
  toolbar,
  state,
  bodyClassName,
  className,
  children,
  ...props
}: WorkspaceShellProps) {
  const titleId = useId();
  const ready = !state || !state.kind || state.kind === "ready";

  return (
    <section
      role="region"
      aria-labelledby={props["aria-label"] ? undefined : titleId}
      className={cx("workspace-shell", className)}
      {...props}
    >
      <header className="workspace-shell__header">
        <div className="workspace-shell__heading">
          <h2 id={titleId} className="workspace-shell__title">
            {title}
          </h2>
          {description ? <p className="workspace-shell__description">{description}</p> : null}
        </div>
        {toolbar ? <div className="workspace-shell__toolbar">{toolbar}</div> : null}
      </header>
      <div className={cx("workspace-shell__body", bodyClassName)}>
        {ready ? children : <div className="workspace-shell__state">{renderState(state)}</div>}
      </div>
    </section>
  );
}

function renderState(state: WorkspaceShellState | undefined) {
  switch (state?.kind) {
    case "loading":
      return <LoadingState label={state.label} />;
    case "empty":
      return <EmptyState title={state.title} description={state.description} action={state.action} />;
    case "error":
      return (
        <ErrorState
          title={state.title}
          description={state.description}
          onRetry={state.onRetry}
          retryLabel={state.retryLabel}
        />
      );
    case "ready":
    default:
      return null;
  }
}
