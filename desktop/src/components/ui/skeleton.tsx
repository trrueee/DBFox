/* Vendored from shadcn/ui Skeleton (MIT): https://github.com/shadcn-ui/ui/blob/main/apps/v4/registry/new-york-v4/ui/skeleton.tsx */
import { cn } from "../../lib/utils";

function ShadcnSkeleton({ className, ...props }: React.ComponentProps<"div">) {
  return <div data-slot="skeleton" className={cn("animate-pulse rounded-md bg-[var(--surface-auxiliary)]", className)} {...props} />;
}

export { ShadcnSkeleton };
