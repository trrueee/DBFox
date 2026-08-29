/*
 * Vendored presentation primitives from shadcn/ui Sidebar (MIT):
 * https://ui.shadcn.com/docs/components/base/sidebar
 * https://ui.shadcn.com/r/styles/new-york-v4/sidebar.json
 *
 * DBFox already owns collapse and pixel width through workspaceStore and
 * react-resizable-panels, so the upstream Provider/cookie/mobile Sheet runtime
 * is intentionally not duplicated. The root is a nav landmark, addressing the
 * upstream SidebarContent landmark limitation while preserving its anatomy.
 */
import { cva, type VariantProps } from "class-variance-authority";
import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from "react";

import { cn } from "../../lib/utils";

function Sidebar({ className, ...props }: HTMLAttributes<HTMLElement>) {
  return (
    <nav
      data-slot="sidebar"
      data-sidebar="sidebar"
      className={cn("flex size-full min-w-0 flex-col overflow-hidden border-r border-[var(--line-subtle)] bg-[var(--surface-navigation)] text-[var(--color-text-secondary)]", className)}
      {...props}
    />
  );
}

function SidebarHeader({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div data-slot="sidebar-header" data-sidebar="header" className={cn("flex shrink-0 flex-col gap-0.5 p-2 pt-2.5", className)} {...props} />;
}

function SidebarFooter({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div data-slot="sidebar-footer" data-sidebar="footer" className={cn("mt-auto flex shrink-0 flex-col gap-0.5 border-t border-[var(--line-subtle)] p-2", className)} {...props} />;
}

function SidebarContent({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div data-slot="sidebar-content" data-sidebar="content" className={cn("flex min-h-0 flex-1 flex-col gap-2 overflow-x-hidden overflow-y-auto px-2 pb-4 [scrollbar-color:var(--color-border-hover)_transparent] [scrollbar-width:thin]", className)} {...props} />;
}

function SidebarGroup({ className, ...props }: HTMLAttributes<HTMLElement>) {
  return <section data-slot="sidebar-group" data-sidebar="group" className={cn("relative mt-4 flex w-full min-w-0 flex-col gap-0.5", className)} {...props} />;
}

function SidebarGroupLabel({ action, children, className }: {
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div data-slot="sidebar-group-label" data-sidebar="group-label" className={cn("flex h-6 shrink-0 items-center justify-between rounded-md px-2 text-[var(--ui-font-micro)] font-medium uppercase leading-4 tracking-[0.04em] text-[var(--color-text-muted)] [&_.dbfox-button]:size-6", className)}>
      <span>{children}</span>
      {action}
    </div>
  );
}

const sidebarMenuButtonVariants = cva(
  "peer/menu-button grid h-8 w-full min-w-0 grid-cols-[16px_minmax(0,1fr)_auto] items-center gap-2 overflow-hidden rounded-[var(--radius-row)] px-2 text-left text-sm text-[var(--color-text-secondary)] outline-none transition-colors hover:bg-[var(--control-bg-hover)] hover:text-[var(--color-text-primary)] focus-visible:shadow-[var(--focus-ring)] disabled:pointer-events-none disabled:opacity-50 data-[active=true]:bg-[var(--nav-active-bg)] data-[active=true]:font-medium data-[active=true]:text-[var(--color-text-primary)] [&>svg]:size-4 [&>svg]:shrink-0",
  {
    variants: {
      emphasis: {
        default: "",
        primary: "font-medium text-[var(--color-text-primary)]",
      },
    },
    defaultVariants: { emphasis: "default" },
  },
);

interface SidebarNavRowProps extends ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof sidebarMenuButtonVariants> {
  icon: ReactNode;
  label: ReactNode;
  meta?: ReactNode;
  active?: boolean;
}

function SidebarNavRow({ icon, label, meta, active = false, emphasis, className, ...props }: SidebarNavRowProps) {
  return (
    <button
      type="button"
      data-slot="sidebar-menu-button"
      data-sidebar="menu-button"
      data-active={active}
      aria-current={active ? "page" : undefined}
      className={cn(sidebarMenuButtonVariants({ emphasis }), className)}
      {...props}
    >
      <span data-sidebar="menu-button-icon" className="inline-flex size-4 items-center justify-center text-[var(--color-text-muted)] [&>svg]:size-4 [&>svg]:stroke-[1.75]" aria-hidden="true">{icon}</span>
      <span data-sidebar="menu-button-label" className="min-w-0 truncate">{label}</span>
      {meta ? <span data-sidebar="menu-button-badge" className="min-w-0 truncate text-[var(--ui-font-micro)] tabular-nums text-[var(--color-text-muted)]">{meta}</span> : null}
    </button>
  );
}

export { Sidebar, SidebarContent, SidebarFooter, SidebarGroup, SidebarGroupLabel, SidebarHeader, SidebarNavRow };
