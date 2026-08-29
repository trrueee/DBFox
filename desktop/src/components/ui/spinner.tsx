/* Vendored from shadcn/ui Spinner (MIT): https://github.com/shadcn-ui/ui/blob/main/apps/v4/registry/new-york-v4/ui/spinner.tsx */
import { Loader2Icon } from "lucide-react";

import { cn } from "../../lib/utils";

function Spinner({ className, ...props }: React.ComponentProps<"svg">) {
  return <Loader2Icon role="status" aria-label="Loading" className={cn("size-4 animate-spin", className)} {...props} />;
}

export { Spinner };
