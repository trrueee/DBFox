import * as React from "react";
import { cn } from "../../lib/utils";

const Input = React.forwardRef<
  HTMLInputElement,
  React.InputHTMLAttributes<HTMLInputElement>
>(({ className, type, ...props }, ref) => {
  return (
    <input
      type={type}
      className={cn(
        "flex h-9 w-full rounded-[var(--radius)] border border-[hsl(var(--input))] bg-transparent px-3 py-1 text-sm transition-all duration-150",
        "placeholder:text-[hsl(var(--muted-foreground))]",
        "hover:border-[hsl(var(--primary)/0.3)]",
        "focus-visible:outline-none focus-visible:border-[hsl(var(--primary)/0.5)] focus-visible:ring-2 focus-visible:ring-[hsl(var(--primary)/0.1)]",
        "disabled:cursor-not-allowed disabled:opacity-50",
        "file:border-0 file:bg-transparent file:text-sm file:font-medium",
        className
      )}
      ref={ref}
      {...props}
    />
  );
});
Input.displayName = "Input";

export { Input };
