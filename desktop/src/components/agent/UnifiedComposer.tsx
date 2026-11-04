import type { FormEvent, KeyboardEvent, ReactNode } from "react";
import { AlertCircle, ChevronDown, LoaderCircle, Plus } from "lucide-react";
import { ReferenceCard } from "../resources/ReferenceCard";
import { referenceKind } from "../resources/resourcePresentation";

import type { WorkbenchReference } from "../../types/workspace";
import type { ConversationDeliveryMode } from "../../types/conversation";
import { PromptInputSubmit, type PromptInputStatus } from "../ai-elements/prompt-input-submit";
import {
  PromptInput,
  PromptInputAction,
  PromptInputActions,
  PromptInputTextarea,
} from "../prompt-kit/prompt-input";
import {
  Button,
  Alert,
  AlertDescription,
  ErrorDetails,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "../ui";
import { getUserErrorMessage } from "../../lib/api/client";
import "./unified-composer.css";

const DELIVERY_LABELS: Record<ConversationDeliveryMode, string> = {
  queue: "排队执行",
  steer: "补充当前任务",
  cancel_and_replace: "停止并替换",
};

interface UnifiedComposerProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void | Promise<void>;
  placeholder: string;
  ariaLabel: string;
  references?: readonly WorkbenchReference[];
  onRemoveReference?: (reference: WorkbenchReference) => void;
  onOpenReference?: (reference: WorkbenchReference) => void;
  onAddAttachment?: () => void;
  attachmentBusy?: boolean;
  attachmentError?: string;
  onRetryAttachment?: () => void;
  running?: boolean;
  submitting?: boolean;
  cancelling?: boolean;
  disabled?: string | null;
  error?: unknown;
  deliveryMode?: ConversationDeliveryMode;
  onDeliveryModeChange?: (mode: ConversationDeliveryMode) => void;
  onCancel?: () => void | Promise<void>;
  autoFocus?: boolean;
  compact?: boolean;
  context?: ReactNode;
}

export function UnifiedComposer({
  value,
  onChange,
  onSubmit,
  placeholder,
  ariaLabel,
  references = [],
  onRemoveReference,
  onOpenReference,
  onAddAttachment,
  attachmentBusy = false,
  attachmentError,
  onRetryAttachment,
  running = false,
  submitting = false,
  cancelling = false,
  disabled,
  error,
  deliveryMode = "queue",
  onDeliveryModeChange,
  onCancel,
  autoFocus = false,
  compact = false,
  context,
}: UnifiedComposerProps) {
  const unavailable = Boolean(disabled) || submitting || attachmentBusy;
  const hasInput = value.trim().length > 0;
  const errorMessage = typeof error === "string"
    ? error
    : error
      ? getUserErrorMessage(error, "消息发送失败，请重试。")
      : null;
  const showStop = running && !hasInput && Boolean(onCancel);
  const actionStatus: PromptInputStatus | undefined = cancelling || submitting
    ? "submitted"
    : showStop
      ? "streaming"
      : error
        ? "error"
        : undefined;

  const submit = (event?: FormEvent) => {
    event?.preventDefault();
    if (!hasInput || unavailable) return;
    void onSubmit();
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Escape" && running && onCancel && !cancelling) {
      event.preventDefault();
      void onCancel();
      return;
    }
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  };

  return (
    <form
      className={`dbfox-composer ${compact ? "dbfox-composer--compact" : ""}`}
      onSubmit={submit}
      aria-label={ariaLabel}
    >
      <PromptInput disabled={Boolean(disabled)} className="dbfox-composer__prompt-input">
        {references.length > 0 ? (
          <div className="dbfox-composer__references" aria-label="当前上下文">
            {references.map((reference) => <ReferenceCard key={referenceKey(reference)}
              name={reference.label} kind={referenceKind(reference)}
              onOpen={onOpenReference ? () => onOpenReference(reference) : undefined}
              onRemove={onRemoveReference ? () => onRemoveReference(reference) : undefined} />)}
          </div>
        ) : null}

        <PromptInputTextarea
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={disabled || placeholder}
          aria-label={ariaLabel}
          disabled={Boolean(disabled) || submitting}
          autoFocus={autoFocus}
        />

        <PromptInputActions className="dbfox-composer__toolbar">
          {onAddAttachment ? <PromptInputAction tooltip="添加本地文件">
            <Button type="button" variant="ghost" size="icon" className="dbfox-composer__attachment-action" aria-label="添加本地文件" aria-busy={attachmentBusy || undefined} disabled={unavailable} onClick={onAddAttachment}>
              {attachmentBusy ? <LoaderCircle className="dbfox-composer__loading" size={20} strokeWidth={1.75} aria-hidden="true" /> : <Plus size={20} strokeWidth={1.75} aria-hidden="true" />}
            </Button>
          </PromptInputAction> : null}
          <span className="dbfox-composer__spacer" aria-hidden="true" />
          {context}

          {running && onDeliveryModeChange ? (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="dbfox-composer__mode"
                  aria-label={`发送方式：${DELIVERY_LABELS[deliveryMode]}`}
                  onClick={(event) => event.stopPropagation()}
                >
                  <span>{DELIVERY_LABELS[deliveryMode]}</span>
                  <ChevronDown size={14} aria-hidden="true" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                {(Object.keys(DELIVERY_LABELS) as ConversationDeliveryMode[]).map((mode) => (
                  <DropdownMenuItem key={mode} onClick={() => onDeliveryModeChange(mode)}>
                    <span className="dbfox-composer__mode-option">
                      <strong>{DELIVERY_LABELS[mode]}</strong>
                      <small>{deliveryDescription(mode)}</small>
                    </span>
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          ) : null}

          <PromptInputAction tooltip={showStop ? "停止当前任务（Esc）" : "发送（Enter）"}>
            <PromptInputSubmit
              status={actionStatus}
              onStop={showStop ? () => void onCancel?.() : undefined}
              className="dbfox-composer__primary-action"
              disabled={showStop ? cancelling : !hasInput || unavailable}
              aria-label={showStop ? "停止当前任务" : submitting ? "正在发送" : `发送：${running ? DELIVERY_LABELS[deliveryMode] : "立即执行"}`}
              aria-busy={submitting || cancelling || undefined}
            />
          </PromptInputAction>
        </PromptInputActions>

        {attachmentError ? <Alert className="dbfox-composer__error" variant="destructive">
          <AlertDescription>{attachmentError}{onRetryAttachment ? <Button type="button" variant="ghost" size="sm" onClick={onRetryAttachment}>重试添加文件</Button> : null}</AlertDescription>
        </Alert> : null}
        {error ? (
          <Alert className="dbfox-composer__error" variant="destructive">
            <AlertCircle aria-hidden="true" />
            <AlertDescription>
              <p>{errorMessage}</p>
              <ErrorDetails error={error} />
            </AlertDescription>
          </Alert>
        ) : null}
      </PromptInput>
    </form>
  );
}

function referenceKey(reference: WorkbenchReference): string {
  if (reference.artifactId) return `artifact:${reference.artifactId}`;
  if (reference.object) return `object:${reference.object.kind}:${reference.object.id}:${reference.object.version ?? ""}`;
  if (reference.authority) return `authority:${reference.authority.kind}:${reference.authority.id}:${reference.locator ?? ""}`;
  return `locator:${reference.locator ?? reference.label}`;
}

function deliveryDescription(mode: ConversationDeliveryMode): string {
  if (mode === "steer") return "把消息补充到正在进行的任务";
  if (mode === "cancel_and_replace") return "停止当前任务并改做这件事";
  return "当前任务完成后继续执行";
}
