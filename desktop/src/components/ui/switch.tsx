/*
 * Vendored from shadcn/ui Switch (MIT):
 * https://github.com/shadcn-ui/ui/blob/main/apps/v4/registry/new-york-v4/ui/switch.tsx
 */
import * as React from "react";
import * as SwitchPrimitive from "@radix-ui/react-switch";

import { cn } from "../../lib/utils";
import "./switch.css";

function Switch({
  className,
  size = "default",
  ...props
}: React.ComponentProps<typeof SwitchPrimitive.Root> & { size?: "sm" | "default" }) {
  return (
    <SwitchPrimitive.Root
      data-slot="switch"
      data-size={size}
      className={cn("dbfox-switch", className)}
      {...props}
    >
      <SwitchPrimitive.Thumb data-slot="switch-thumb" className="dbfox-switch__thumb" />
    </SwitchPrimitive.Root>
  );
}

export { Switch };
