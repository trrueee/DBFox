import * as React from "react";
import { cn } from "../../lib/utils";
import "./toolbar.css";

const Toolbar = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      role="toolbar"
      className={cn("dbfox-toolbar", className)}
      {...props}
    />
  )
);
Toolbar.displayName = "Toolbar";

const ToolbarTitle = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn("dbfox-toolbar__title", className)}
      {...props}
    />
  )
);
ToolbarTitle.displayName = "ToolbarTitle";

const ToolbarGroup = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("dbfox-toolbar__group", className)} {...props} />
  )
);
ToolbarGroup.displayName = "ToolbarGroup";

export { Toolbar, ToolbarGroup, ToolbarTitle };
