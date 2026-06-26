import * as React from "react";
import {
  Group,
  Panel,
  Separator,
  type GroupProps,
  type Orientation,
  type PanelProps,
  type SeparatorProps,
} from "react-resizable-panels";
import { cn } from "../../lib/utils";
import "./resizable.css";

type ResizablePanelGroupProps = Omit<GroupProps, "elementRef" | "orientation"> & {
  direction?: Orientation;
};

const ResizablePanelGroup = React.forwardRef<HTMLDivElement, ResizablePanelGroupProps>(
  ({ className, direction = "horizontal", resizeTargetMinimumSize, ...props }, ref) => (
    <Group
      elementRef={ref}
      orientation={direction}
      resizeTargetMinimumSize={resizeTargetMinimumSize ?? { fine: 8, coarse: 28 }}
      className={cn("dbfox-resizable-panel-group", className)}
      {...props}
    />
  ),
);
ResizablePanelGroup.displayName = "ResizablePanelGroup";

type ResizablePanelProps = Omit<PanelProps, "elementRef">;

const ResizablePanel = React.forwardRef<HTMLDivElement, ResizablePanelProps>(
  ({ className, ...props }, ref) => (
    <Panel
      elementRef={ref}
      className={cn("dbfox-resizable-panel", className)}
      {...props}
    />
  ),
);
ResizablePanel.displayName = "ResizablePanel";

type ResizableHandleProps = Omit<SeparatorProps, "elementRef"> & {
  withGrip?: boolean;
};

const ResizableHandle = React.forwardRef<HTMLDivElement, ResizableHandleProps>(
  ({ className, children, withGrip = true, ...props }, ref) => (
    <Separator
      elementRef={ref}
      className={cn("dbfox-resizable-handle", className)}
      {...props}
    >
      <span className="dbfox-resizable-handle__rail" aria-hidden="true" />
      {withGrip && <span className="dbfox-resizable-handle__grip" aria-hidden="true" />}
      {children}
    </Separator>
  ),
);
ResizableHandle.displayName = "ResizableHandle";

export { ResizableHandle, ResizablePanel, ResizablePanelGroup };
export type { ResizableHandleProps, ResizablePanelGroupProps, ResizablePanelProps };
