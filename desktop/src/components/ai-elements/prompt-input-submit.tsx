/*
 * Vendored from Vercel AI Elements' Apache-2.0 PromptInputSubmit.
 * Upstream: https://github.com/vercel/chatbot/blob/main/components/ai-elements/prompt-input.tsx
 *
 * DBFox supplies its existing Button primitive and runtime-neutral status;
 * the upstream single-control submit/stop behavior is retained.
 */
import { useCallback } from "react";
import type { ComponentProps, MouseEvent } from "react";
import { ArrowUp, LoaderCircle, Square, X } from "lucide-react";

import { Button } from "../ui";

export type PromptInputStatus = "submitted" | "streaming" | "error" | "ready";

export type PromptInputSubmitProps = ComponentProps<typeof Button> & {
  status?: PromptInputStatus;
  onStop?: () => void;
};

export function PromptInputSubmit({
  children,
  onClick,
  onStop,
  size = "icon-sm",
  status,
  variant = "default",
  ...props
}: PromptInputSubmitProps) {
  const isGenerating = status === "submitted" || status === "streaming";

  let icon = <ArrowUp size={16} aria-hidden="true" />;
  if (status === "submitted") {
    icon = <LoaderCircle className="animate-spin" size={16} aria-hidden="true" />;
  } else if (status === "streaming") {
    icon = <Square size={14} fill="currentColor" aria-hidden="true" />;
  } else if (status === "error") {
    icon = <X size={16} aria-hidden="true" />;
  }

  const handleClick = useCallback((event: MouseEvent<HTMLButtonElement>) => {
    if (isGenerating && onStop) {
      event.preventDefault();
      onStop();
      return;
    }
    onClick?.(event);
  }, [isGenerating, onClick, onStop]);

  return (
    <Button
      aria-label={isGenerating ? "Stop" : "Submit"}
      onClick={handleClick}
      size={size}
      type={isGenerating && onStop ? "button" : "submit"}
      variant={variant}
      {...props}
    >
      {children ?? icon}
    </Button>
  );
}
