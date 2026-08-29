/*
 * Vendored from Prompt Kit's MIT-licensed PromptInput.
 * Upstream: https://github.com/ibelick/prompt-kit/blob/main/components/prompt-kit/prompt-input.tsx
 *
 * Local changes are limited to DBFox's semantic theme tokens and CSP-safe
 * native field sizing. The public composition model and interaction anatomy
 * remain the upstream component's.
 */
import React, { createContext, useContext, useRef, useState } from "react";

import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "../ui";
import { cn } from "../../lib/utils";

type PromptInputContextValue = {
  disabled: boolean;
  textareaRef: React.RefObject<HTMLTextAreaElement | null>;
};

const PromptInputContext = createContext<PromptInputContextValue>({
  disabled: false,
  textareaRef: React.createRef<HTMLTextAreaElement>(),
});

function usePromptInput() {
  return useContext(PromptInputContext);
}

export type PromptInputProps = React.ComponentProps<"div"> & {
  disabled?: boolean;
};

export function PromptInput({
  children,
  className,
  disabled = false,
  onClick,
  ...props
}: PromptInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const handleClick: React.MouseEventHandler<HTMLDivElement> = (event) => {
    if (!disabled) textareaRef.current?.focus();
    onClick?.(event);
  };

  return (
    <TooltipProvider>
      <PromptInputContext.Provider value={{ disabled, textareaRef }}>
        <div
          className={cn(
            "cursor-text rounded-2xl border border-[var(--control-border)] bg-[var(--agent-surface-elevated)] p-2 shadow-[var(--shadow-sm)] transition-[border-color,box-shadow] duration-200 focus-within:border-[color-mix(in_srgb,var(--color-primary)_58%,var(--control-border))] focus-within:shadow-[var(--shadow-sm),var(--focus-ring)]",
            disabled && "cursor-not-allowed opacity-60",
            className,
          )}
          onClick={handleClick}
          {...props}
        >
          {children}
        </div>
      </PromptInputContext.Provider>
    </TooltipProvider>
  );
}

export type PromptInputTextareaProps = React.ComponentProps<"textarea">;

export function PromptInputTextarea({ className, ...props }: PromptInputTextareaProps) {
  const { disabled, textareaRef } = usePromptInput();
  return (
    <textarea
      ref={textareaRef}
      className={cn(
        "min-h-12 max-h-40 w-full resize-none overflow-y-auto border-0 bg-transparent px-1 pt-1 text-[length:var(--ui-font-body)] leading-[1.55] text-[var(--color-text-primary)] shadow-none outline-none [field-sizing:content] placeholder:text-[var(--color-text-muted)] focus-visible:ring-0",
        className,
      )}
      disabled={disabled || props.disabled}
      rows={1}
      {...props}
    />
  );
}

export type PromptInputActionsProps = React.HTMLAttributes<HTMLDivElement>;

export function PromptInputActions({ children, className, ...props }: PromptInputActionsProps) {
  return (
    <div className={cn("flex min-w-0 items-center gap-2", className)} {...props}>
      {children}
    </div>
  );
}

export type PromptInputActionProps = React.ComponentProps<typeof Tooltip> & {
  className?: string;
  tooltip: React.ReactNode;
  children: React.ReactNode;
  side?: "top" | "bottom" | "left" | "right";
};

export function PromptInputAction({
  children,
  className,
  side = "top",
  tooltip,
  ...props
}: PromptInputActionProps) {
  const { disabled } = usePromptInput();
  const [open, setOpen] = useState(false);
  return (
    <Tooltip open={open} onOpenChange={setOpen} {...props}>
      <TooltipTrigger
        asChild
        disabled={disabled}
        onClick={(event) => {
          event.stopPropagation();
          setOpen(false);
        }}
      >
        {children}
      </TooltipTrigger>
      <TooltipContent side={side} className={className}>
        {tooltip}
      </TooltipContent>
    </Tooltip>
  );
}
