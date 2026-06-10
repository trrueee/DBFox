import type { ReactNode } from "react";
import "./workbench.css";

interface WorkbenchShellProps {
  menuBar: ReactNode;
  sidebar: ReactNode;
  main: ReactNode;
  assistant: ReactNode;
  statusBar: ReactNode;
  assistantCollapsed: boolean;
}

export function WorkbenchShell({
  menuBar,
  sidebar,
  main,
  assistant,
  statusBar,
  assistantCollapsed,
}: WorkbenchShellProps) {
  return (
    <div className="workbench-root">
      {menuBar}
      <main className={`workbench-shell ${assistantCollapsed ? "workbench-shell--agent-collapsed" : ""}`}>
        <aside className="workbench-sidebar">{sidebar}</aside>
        <section className="workbench-main">{main}</section>
        <aside className="workbench-agent">{assistant}</aside>
      </main>
      {statusBar}
    </div>
  );
}
