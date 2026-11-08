/*
 * Production question card based on Agent Elements QuestionTool and
 * QuestionPrompt registry source (MIT):
 * https://agent-elements.21st.dev/docs/question-tool
 * https://agent-elements.21st.dev/r/question-tool.json
 *
 * DBFox QuestionItem remains the sole contract. The upstream local multi-page
 * question registry is intentionally not copied because each durable DBFox
 * item represents one question. Radix RadioGroup retains proven radio-keyboard
 * semantics inside the adopted card/option/action anatomy.
 */
import * as RadioGroup from "@radix-ui/react-radio-group";
import {
  CheckCircleIcon,
  ProhibitIcon,
  ClockIcon,
  QuestionIcon,
  CircleNotchIcon,
  WarningIcon,
} from "@/components/icons";
import { useEffect, useRef, useState } from "react";

import type { QuestionItem } from "../../types/conversation";
import { getUserErrorMessage } from "../../lib/api/client";
import { Alert, AlertDescription } from "../ui/alert";
import { Button } from "../ui/button";
import { ErrorDetails } from "../ui/error-details";
import "./agent-interaction.css";

export function AgentQuestion({
  question,
  onRespond,
  submitting = false,
  error,
}: {
  question: QuestionItem;
  onRespond: (response: { selected_value?: string; text?: string }) => Promise<void> | void;
  submitting?: boolean;
  error?: unknown;
}) {
  const [selectedValue, setSelectedValue] = useState("");
  const [text, setText] = useState("");
  const pending = question.status === "waiting";
  const firstControlRef = useRef<HTMLButtonElement | HTMLTextAreaElement>(null);

  useEffect(() => {
    if (pending && document.activeElement === document.body) firstControlRef.current?.focus({ preventScroll: true });
  }, [pending, question.id]);

  const responseText = text.trim();
  const canSubmit = pending && !submitting && Boolean(selectedValue || responseText);
  const submit = () => {
    if (!canSubmit) return;
    void Promise.resolve(onRespond({
      ...(selectedValue ? { selected_value: selectedValue } : {}),
      ...(responseText ? { text: responseText } : {}),
    })).catch(() => undefined);
  };

  return (
    <section
      className="agent-question"
      aria-label="需要补充信息"
      aria-live="polite"
      aria-busy={submitting || undefined}
      data-status={question.status}
    >
      <header className="flex min-h-8 items-center justify-between gap-2 border-b border-[var(--agent-border)] px-3 text-xs text-[var(--agent-text-muted)]">
        <span className="inline-flex items-center gap-1.5">
          <QuestionStatusIcon status={question.status} />
          {questionStatusLabel(question.status)}
        </span>
      </header>

      {pending ? (
        <div className="grid gap-3 bg-[var(--agent-surface-elevated)] p-3">
          <div className="grid gap-2">
            <div className="grid gap-1">
              <strong className="text-sm font-medium text-[var(--agent-text)]">{question.payload.question}</strong>
              {question.payload.reason ? <span className="text-xs text-[var(--agent-text-muted)]">{question.payload.reason}</span> : null}
            </div>
          </div>

          {question.payload.options.length > 0 ? (
            <RadioGroup.Root
              className="grid gap-1"
              aria-label={question.payload.question}
              value={selectedValue}
              onValueChange={setSelectedValue}
              disabled={submitting}
            >
              {question.payload.options.map((option, index) => {
                const optionId = `${question.id}-${index}`;
                const selected = option.value === selectedValue;
                return (
                  <label
                    key={option.value}
                    htmlFor={optionId}
                    className="agent-question__option"
                    data-selected={selected || undefined}
                  >
                    <RadioGroup.Item
                      ref={index === 0 ? firstControlRef as React.Ref<HTMLButtonElement> : undefined}
                      id={optionId}
                      value={option.value}
                      aria-describedby={option.description ? `${optionId}-description` : undefined}
                      className="agent-question__radio"
                    >
                      <RadioGroup.Indicator className="agent-question__radio-dot" />
                    </RadioGroup.Item>
                    <span className="grid gap-0.5 text-sm text-[var(--agent-text)]">
                      <span>{option.label}</span>
                      {option.description ? <small id={`${optionId}-description`} className="text-xs text-[var(--agent-text-muted)]">{option.description}</small> : null}
                      {selected ? <span className="sr-only">当前选项</span> : null}
                    </span>
                  </label>
                );
              })}
            </RadioGroup.Root>
          ) : null}

          {question.payload.allow_free_text ? (
            <textarea
              ref={question.payload.options.length === 0 ? firstControlRef as React.Ref<HTMLTextAreaElement> : undefined}
              aria-label="补充说明"
              value={text}
              onChange={(event) => setText(event.target.value)}
              placeholder={question.payload.options.length > 0 ? "也可以补充说明" : "输入你的回答"}
              disabled={submitting}
              rows={3}
              className="min-h-16 w-full resize-y rounded-md border border-[var(--agent-border)] bg-[var(--control-bg)] px-2.5 py-2 text-sm text-[var(--agent-text)] outline-none placeholder:text-[var(--agent-text-muted)] focus-visible:shadow-[var(--focus-ring)]"
            />
          ) : null}

          {error ? (
            <Alert variant="destructive" className="py-2">
              <AlertDescription>
                <p>{typeof error === "string" ? error : getUserErrorMessage(error, "回答提交失败，请重试。")}</p>
                <ErrorDetails error={error} />
              </AlertDescription>
            </Alert>
          ) : null}

          <div className="flex justify-end">
            <Button type="button" size="sm" onClick={submit} disabled={!canSubmit}>
              {submitting ? <CircleNotchIcon className="animate-spin" aria-hidden="true" /> : null}
              {submitting ? "正在提交…" : "继续任务"}
            </Button>
          </div>
        </div>
      ) : (
        <QuestionOutcome question={question} />
      )}
    </section>
  );
}

function QuestionOutcome({ question }: { question: QuestionItem }) {
  if (question.status === "completed") {
    return (
      <div className="bg-[var(--agent-surface-elevated)] px-3 py-2 text-sm text-[var(--agent-text-secondary)]">
        {questionResponseLabel(question)}
      </div>
    );
  }

  const message = question.status === "expired"
    ? "回答期限已结束。当前任务不会继续接受这条回答；如仍需处理，请重新发起任务。"
    : question.status === "cancelled"
      ? "这个问题已随任务停止，不再接受回答。"
      : question.status === "failed"
        ? "这个问题未能完成。请根据任务错误提示继续处理。"
        : "问题等待状态已经结束，请刷新任务查看最新状态。";
  return (
    <div className="bg-[var(--agent-surface-elevated)] px-3 py-2 text-sm text-[var(--agent-text-secondary)]">
      {message}
    </div>
  );
}

function QuestionStatusIcon({ status }: { status: QuestionItem["status"] }) {
  if (status === "completed") return <CheckCircleIcon className="size-3.5 text-[var(--color-success)]" aria-hidden="true" />;
  if (status === "expired") return <ClockIcon className="size-3.5 text-[var(--color-warning)]" aria-hidden="true" />;
  if (status === "cancelled") return <ProhibitIcon className="size-3.5" aria-hidden="true" />;
  if (status === "failed") return <WarningIcon className="size-3.5 text-[var(--color-danger)]" aria-hidden="true" />;
  return <QuestionIcon className="size-3.5" aria-hidden="true" />;
}

function questionStatusLabel(status: QuestionItem["status"]): string {
  if (status === "completed") return "已回答";
  if (status === "expired") return "问题已过期";
  if (status === "cancelled") return "问题已取消";
  if (status === "failed") return "问题未完成";
  return "问题";
}

function questionResponseLabel(question: QuestionItem): string {
  if (!question.payload.response || typeof question.payload.response !== "object") return "已回答";
  const response = question.payload.response;
  const selectedValue = typeof response.selected_value === "string" ? response.selected_value : "";
  const selectedLabel = question.payload.options.find((option) => option.value === selectedValue)?.label || selectedValue;
  const text = typeof response.text === "string" ? response.text.trim() : "";
  return [selectedLabel, text].filter(Boolean).join(" · ") || "已回答";
}
