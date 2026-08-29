/* Radix Toolbar 1.1 presentation boundary: roving focus and keyboard navigation remain upstream-owned. */
import * as React from "react";
import * as ToolbarPrimitive from "@radix-ui/react-toolbar";

import { cn } from "../../lib/utils";
import "./toolbar.css";

const Toolbar = React.forwardRef<
  React.ComponentRef<typeof ToolbarPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof ToolbarPrimitive.Root>
>(({ className, ...props }, ref) => (
  <ToolbarPrimitive.Root ref={ref} className={cn("dbfox-toolbar", className)} {...props} />
));
Toolbar.displayName = ToolbarPrimitive.Root.displayName;

const ToolbarButton = ToolbarPrimitive.Button;
const ToolbarLink = ToolbarPrimitive.Link;
const ToolbarSeparator = ToolbarPrimitive.Separator;
const ToolbarToggleGroup = ToolbarPrimitive.ToggleGroup;
const ToolbarToggleItem = ToolbarPrimitive.ToggleItem;

const ToolbarTitle = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("dbfox-toolbar__title", className)} {...props} />
  ),
);
ToolbarTitle.displayName = "ToolbarTitle";

const ToolbarGroup = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} role="group" className={cn("dbfox-toolbar__group", className)} {...props} />
  ),
);
ToolbarGroup.displayName = "ToolbarGroup";

export {
  Toolbar,
  ToolbarButton,
  ToolbarGroup,
  ToolbarLink,
  ToolbarSeparator,
  ToolbarTitle,
  ToolbarToggleGroup,
  ToolbarToggleItem,
};
