import type { FormEvent, KeyboardEvent } from "react";
import { AlertCircle, ChevronDown, X } from "lucide-react";

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
}

export function UnifiedComposer({
  value,
  onChange,
  onSubmit,
  placeholder,
  ariaLabel,
  references = [],
  onRemoveReference,
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
}: UnifiedComposerProps) {
  const unavailable = Boolean(disabled) || submitting;
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
            {references.map((reference) => (
              <span className="dbfox-reference-chip" key={referenceKey(reference)}>
                <span className="dbfox-reference-chip__kind">
                  {reference.object?.kind || reference.authority?.kind || (reference.artifactId ? "工件" : "上下文")}
                </span>
                <span className="dbfox-reference-chip__label" title={reference.label}>
                  {reference.label}
                </span>
                {onRemoveReference ? (
                  <button
                    type="button"
                    className="dbfox-reference-chip__remove"
                    onClick={(event) => { event.stopPropagation(); onRemoveReference(reference); }}
                    aria-label={`移除上下文：${reference.label}`}
                  >
                    <X size={14} aria-hidden="true" />
                  </button>
                ) : null}
              </span>
            ))}
          </div>
        ) : null}

        <PromptInputTextarea
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={disabled || placeholder}
          aria-label={ariaLabel}
          disabled={unavailable}
          autoFocus={autoFocus}
        />

        <PromptInputActions className="dbfox-composer__toolbar">
          <span className="dbfox-composer__spacer" aria-hidden="true" />

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
