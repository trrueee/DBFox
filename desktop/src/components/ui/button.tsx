import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import type { ClassValue } from "clsx";
import { cn } from "../../lib/utils";
import "./button.css";

type ButtonVariant = "default" | "destructive" | "outline" | "secondary" | "ghost" | "link";
type ButtonSize = "default" | "sm" | "lg" | "icon" | "icon-sm";

interface ButtonVariantOptions {
  variant?: ButtonVariant | null;
  size?: ButtonSize | null;
  className?: ClassValue;
}

const buttonVariantClasses: Record<ButtonVariant, string> = {
  default: "dbfox-button--default",
  destructive: "dbfox-button--destructive",
  outline: "dbfox-button--outline",
  secondary: "dbfox-button--secondary",
  ghost: "dbfox-button--ghost",
  link: "dbfox-button--link",
};

const buttonSizeClasses: Record<ButtonSize, string> = {
  default: "dbfox-button--default-size",
  sm: "dbfox-button--sm",
  lg: "dbfox-button--lg",
  icon: "dbfox-button--icon",
  "icon-sm": "dbfox-button--icon-sm",
};

function buttonVariants({ variant, size, className }: ButtonVariantOptions = {}) {
  const normalizedVariant = variant ?? "default";
  const normalizedSize = size ?? "default";

  return cn(
    "dbfox-button",
    buttonVariantClasses[normalizedVariant],
    buttonSizeClasses[normalizedSize],
    className
  );
}

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant | null;
  size?: ButtonSize | null;
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    );
  }
);
Button.displayName = "Button";

export { Button, buttonVariants };
