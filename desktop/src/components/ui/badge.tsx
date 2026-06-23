import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "../../lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-[var(--radius)] px-2 py-0.5 text-[var(--ui-font-control)] font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-[hsl(var(--ring))]",
  {
    variants: {
      variant: {
        default:
          "bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))]",
        secondary:
          "bg-[hsl(var(--secondary))] text-[hsl(var(--secondary-foreground))]",
        success:
          "bg-[hsl(var(--success)/0.15)] text-[hsl(var(--success))]",
        warning:
          "bg-[hsl(var(--warning)/0.15)] text-[hsl(var(--warning))]",
        destructive:
          "bg-[hsl(var(--destructive)/0.15)] text-[hsl(var(--destructive))]",
        outline:
          "border border-[hsl(var(--border))] text-[hsl(var(--muted-foreground))]",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}

export { Badge, badgeVariants };
