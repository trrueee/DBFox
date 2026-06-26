import * as React from "react";
import { cn } from "../../lib/utils";
import "./panel.css";

type PanelProps = React.HTMLAttributes<HTMLElement>;

const Panel = React.forwardRef<HTMLElement, PanelProps>(({ className, ...props }, ref) => (
  <section
    ref={ref}
    role={props["aria-label"] || props["aria-labelledby"] ? "region" : undefined}
    className={cn("dbfox-panel", className)}
    {...props}
  />
));
Panel.displayName = "Panel";

const PanelHeader = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn("dbfox-panel__header", className)}
      {...props}
    />
  )
);
PanelHeader.displayName = "PanelHeader";

const PanelTitle = React.forwardRef<HTMLHeadingElement, React.HTMLAttributes<HTMLHeadingElement>>(
  ({ className, ...props }, ref) => (
    <h2
      ref={ref}
      className={cn("dbfox-panel__title", className)}
      {...props}
    />
  )
);
PanelTitle.displayName = "PanelTitle";

const PanelDescription = React.forwardRef<HTMLParagraphElement, React.HTMLAttributes<HTMLParagraphElement>>(
  ({ className, ...props }, ref) => (
    <p
      ref={ref}
      className={cn("dbfox-panel__description", className)}
      {...props}
    />
  )
);
PanelDescription.displayName = "PanelDescription";

const PanelBody = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("dbfox-panel__body", className)} {...props} />
  )
);
PanelBody.displayName = "PanelBody";

const PanelFooter = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn("dbfox-panel__footer", className)}
      {...props}
    />
  )
);
PanelFooter.displayName = "PanelFooter";

export { Panel, PanelBody, PanelDescription, PanelFooter, PanelHeader, PanelTitle };
