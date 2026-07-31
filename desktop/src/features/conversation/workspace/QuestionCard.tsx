import { HelpCircle } from "lucide-react";
import * as RadioGroup from "@radix-ui/react-radio-group";
import { useEffect, useRef, useState } from "react";
import type { QuestionItem } from "../../../types/conversation";

export function QuestionCard({
  question,
  onRespond,
  submitting = false,
  error,
}: {
  question: QuestionItem;
  onRespond: (response: { selected_value?: string; text?: string }) => Promise<void> | void;
  submitting?: boolean;
  error?: string | null;
}) {
  const [selectedValue, setSelectedValue] = useState("");
  const [text, setText] = useState("");
  const pending = question.status === "waiting";
  const firstControlRef = useRef<HTMLButtonElement | HTMLTextAreaElement>(null);
  useEffect(() => {
    if (pending) firstControlRef.current?.focus({ preventScroll: true });
  }, [pending, question.id]);
  const submit = () => {
    const responseText = text.trim();
    if (!pending || submitting || (!selectedValue && !responseText)) return;
    void Promise.resolve(onRespond({
      ...(selectedValue ? { selected_value: selectedValue } : {}),
      ...(responseText ? { text: responseText } : {}),
    })).catch(() => undefined);
  };

  return (
    <section className={`conv-question-card is-${question.status}`} aria-label="需要补充信息" aria-live="polite">
      <header>
        <HelpCircle size={17} aria-hidden="true" />
        <strong>{pending ? "需要你补充一个信息" : "已补充信息"}</strong>
      </header>
      <p className="conv-question-prompt">{question.payload.question}</p>
      <p className="conv-question-reason">{question.payload.reason}</p>
      {pending ? (
        <>
          {question.payload.options.length > 0 && (
            <RadioGroup.Root
              className="conv-question-options"
              aria-label={question.payload.question}
              value={selectedValue}
              onValueChange={setSelectedValue}
              disabled={submitting}
            >
              {question.payload.options.map((option, index) => (
                <div key={option.value} className="conv-question-option">
                  <RadioGroup.Item
                    ref={index === 0 ? firstControlRef as React.Ref<HTMLButtonElement> : undefined}
                    id={`${question.id}-${index}`}
                    value={option.value}
                    aria-describedby={option.description ? `${question.id}-${index}-description` : undefined}
                  >
                    <RadioGroup.Indicator />
                  </RadioGroup.Item>
                  <label htmlFor={`${question.id}-${index}`}>
                    <strong>{option.label}</strong>
                    {option.description && <small id={`${question.id}-${index}-description`}>{option.description}</small>}
                  </label>
                </div>
              ))}
            </RadioGroup.Root>
          )}
          {question.payload.allow_free_text && (
            <textarea
              ref={question.payload.options.length === 0 ? firstControlRef as React.Ref<HTMLTextAreaElement> : undefined}
              aria-label="补充说明"
              value={text}
              onChange={(event) => setText(event.target.value)}
              placeholder="也可以直接输入你的口径或要求"
              disabled={submitting}
              rows={2}
            />
          )}
          {error && <p className="conv-action-error" role="alert">{error}</p>}
          <button
            type="button"
            onClick={submit}
            disabled={submitting || (!selectedValue && !text.trim())}
          >
            {submitting ? "正在提交…" : "继续分析"}
          </button>
        </>
      ) : (
        <p className="conv-question-response">
          {questionResponseLabel(question)}
        </p>
      )}
    </section>
  );
}

function questionResponseLabel(question: QuestionItem): string {
  if (!question.payload.response || typeof question.payload.response !== "object") return "已回答";
  const response = question.payload.response;
  const selectedValue = typeof response.selected_value === "string" ? response.selected_value : "";
  const selectedLabel = question.payload.options.find((option) => option.value === selectedValue)?.label || selectedValue;
  const text = typeof response.text === "string" ? response.text.trim() : "";
  return [selectedLabel, text].filter(Boolean).join(" · ") || "已回答";
}
