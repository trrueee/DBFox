import { ArrowUp } from "lucide-react";
import { Button } from "../../../components/ui";
import "../SmartQueryHome.css";

interface AskInputBoxProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
}

export function AskInputBox({ value, onChange, onSubmit }: AskInputBoxProps) {
  return (
    <div className="ask-input">
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
