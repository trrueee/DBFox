/*
 * Vendored from shadcn/ui Progress (MIT) on top of Radix Progress:
 * https://github.com/shadcn-ui/ui/blob/main/apps/v4/registry/new-york-v4/ui/progress.tsx
 *
 * DBFox startup progress is intentionally indeterminate: the engine exposes
 * phases, not trustworthy percentages. The upstream inline transform is
 * replaced by a CSS animation because the desktop CSP forbids style attrs.
 */
import * as React from "react";
import * as ProgressPrimitive from "@radix-ui/react-progress";

import { cn } from "../../lib/utils";

function Progress({ className, ...props }: Omit<React.ComponentProps<typeof ProgressPrimitive.Root>, "value">) {
  return (
    <ProgressPrimitive.Root
      data-slot="progress"
      value={null}
      className={cn("relative h-2 w-full overflow-hidden rounded-full bg-[var(--color-primary-soft)]", className)}
      {...props}
    >
      <ProgressPrimitive.Indicator
        data-slot="progress-indicator"
        className="dbfox-indeterminate-progress h-full w-1/3 rounded-full bg-[var(--color-primary)]"
      />
    </ProgressPrimitive.Root>
  );
}

export { Progress };
