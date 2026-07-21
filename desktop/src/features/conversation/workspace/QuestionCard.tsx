import { HelpCircle } from "lucide-react";
import * as RadioGroup from "@radix-ui/react-radio-group";
import { useEffect, useRef, useState } from "react";
import type { ConversationQuestion } from "../../../types/conversation";

export function QuestionCard({
  question,
  onRespond,
}: {
  question: ConversationQuestion;
  onRespond: (response: { selected_value?: string; text?: string }) => void;
}) {
  const [selectedValue, setSelectedValue] = useState("");
  const [text, setText] = useState("");
  const pending = question.status === "pending";
  const firstControlRef = useRef<HTMLButtonElement | HTMLTextAreaElement>(null);
  useEffect(() => {
    if (pending) firstControlRef.current?.focus({ preventScroll: true });
  }, [pending, question.id]);
  const submit = () => {
    const responseText = text.trim();
    if (!pending || (!selectedValue && !responseText)) return;
    onRespond({
      ...(selectedValue ? { selected_value: selectedValue } : {}),
      ...(responseText ? { text: responseText } : {}),
    });
  };

  return (
    <section className={`conv-question-card is-${question.status}`} aria-label="需要补充信息" aria-live="polite">
      <header>
        <HelpCircle size={17} aria-hidden="true" />
        <strong>{pending ? "需要你补充一个信息" : "已补充信息"}</strong>
      </header>
      <p className="conv-question-prompt">{question.question}</p>
      <p className="conv-question-reason">{question.reason}</p>
      {pending ? (
        <>
          {question.options.length > 0 && (
            <RadioGroup.Root
              className="conv-question-options"
              aria-label={question.question}
              value={selectedValue}
              onValueChange={setSelectedValue}
            >
              {question.options.map((option, index) => (
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
          {question.allow_free_text && (
            <textarea
              ref={question.options.length === 0 ? firstControlRef as React.Ref<HTMLTextAreaElement> : undefined}
              aria-label="补充说明"
              value={text}
              onChange={(event) => setText(event.target.value)}
              placeholder="也可以直接输入你的口径或要求"
              rows={2}
            />
          )}
          <button type="button" onClick={submit} disabled={!selectedValue && !text.trim()}>
            继续分析
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

function questionResponseLabel(question: ConversationQuestion): string {
  if (!question.response || typeof question.response !== "object") return "已回答";
  const response = question.response as Record<string, unknown>;
  const selectedValue = typeof response.selected_value === "string" ? response.selected_value : "";
  const selectedLabel = question.options.find((option) => option.value === selectedValue)?.label || selectedValue;
  const text = typeof response.text === "string" ? response.text.trim() : "";
  return [selectedLabel, text].filter(Boolean).join(" · ") || "已回答";
}
