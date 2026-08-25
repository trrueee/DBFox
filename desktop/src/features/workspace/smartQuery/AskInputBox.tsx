import { ArrowUp } from "lucide-react";
import { Button } from "../../../components/ui";
import type { WorkbenchReference } from "../../../../../sdk/frontend/index";
import "../SmartQueryHome.css";

interface AskInputBoxProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  projectId?: string;
  reference?: WorkbenchReference | null;
  onClearReference?: () => void;
}

export function AskInputBox({
  value,
  onChange,
  onSubmit,
  reference,
  onClearReference,
}: AskInputBoxProps) {
  return (
    <div className="ask-input">
      {reference && (
        <div className="ask-input__reference" aria-label="当前引用语境">
          <span>{reference.label}</span>
          {onClearReference && (
            <button type="button" onClick={onClearReference} aria-label="清除引用">×</button>
          )}
        </div>
      )}
      <textarea
        className="ask-input__textarea"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            onSubmit();
          }
        }}
        placeholder="用自然语言提问，例如：查询用户表中最近一周的新注册用户数量"
      />
      <Button
        type="button"
        className="ask-input__send"
        size="icon-sm"
        onClick={onSubmit}
        aria-label="发送问题"
        title="发送问题"
      >
        <ArrowUp size={16} />
      </Button>
    </div>
  );
}

