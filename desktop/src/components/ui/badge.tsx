import * as React from "react";
import type { ClassValue } from "clsx";
import { cn } from "../../lib/utils";
import "./badge.css";

type BadgeVariant = "default" | "secondary" | "success" | "warning" | "destructive" | "outline";

interface BadgeVariantOptions {
  variant?: BadgeVariant | null;
  className?: ClassValue;
}

const badgeVariantClasses: Record<BadgeVariant, string> = {
  default: "dbfox-badge--default",
  secondary: "dbfox-badge--secondary",
  success: "dbfox-badge--success",
  warning: "dbfox-badge--warning",
  destructive: "dbfox-badge--destructive",
  outline: "dbfox-badge--outline",
};

function badgeVariants({ variant, className }: BadgeVariantOptions = {}) {
  return cn("dbfox-badge", badgeVariantClasses[variant ?? "default"], className);
}

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: BadgeVariant | null;
}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}

export { Badge, badgeVariants };
