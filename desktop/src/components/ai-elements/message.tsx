/**
 * Vendored presentation subset from Vercel AI Elements Message.
 * Upstream: https://elements.ai-sdk.dev/components/message
 * Registry: https://elements.ai-sdk.dev/api/registry/message.json
 * License: Apache-2.0
 *
 * DBFox keeps its sanitized Markdown renderer and durable message contract;
 * only the upstream Message/Content/Actions anatomy is adopted here.
 */
import type { ComponentProps, HTMLAttributes } from "react";
import { cn } from "../../lib/utils";
import { Button, type ButtonProps } from "../ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "../ui/tooltip";
import "./message.css";

export type MessageProps = HTMLAttributes<HTMLDivElement> & {
  from: "user" | "assistant";
};

export const Message = ({ className, from, ...props }: MessageProps) => (
  <div
    className={cn(
      "dbfox-message",
      from === "user" ? "dbfox-message--user" : "dbfox-message--assistant",
      className,
    )}
    data-message-role={from}
    {...props}
  />
);

export type MessageContentProps = HTMLAttributes<HTMLDivElement>;

export const MessageContent = ({
  children,
  className,
  ...props
}: MessageContentProps) => (
  <div className={cn("dbfox-message__content", className)} {...props}>
    {children}
  </div>
);

export type MessageActionsProps = ComponentProps<"div">;

export const MessageActions = ({
  className,
  children,
  ...props
}: MessageActionsProps) => (
  <div className={cn("dbfox-message__actions", className)} {...props}>
    {children}
  </div>
);

export type MessageActionProps = ButtonProps & {
  tooltip?: string;
  label?: string;
};

export const MessageAction = ({
  tooltip,
  children,
  label,
  variant = "ghost",
  size = "icon",
  ...props
}: MessageActionProps) => {
  const button = (
    <Button size={size} type="button" variant={variant} {...props}>
      {children}
      <span className="sr-only">{label || tooltip}</span>
    </Button>
  );

  if (!tooltip) return button;
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>{button}</TooltipTrigger>
        <TooltipContent>{tooltip}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
};
