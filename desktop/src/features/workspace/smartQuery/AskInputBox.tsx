import { ArrowUp } from "lucide-react";

interface AskInputBoxProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
}

export function AskInputBox({ value, onChange, onSubmit }: AskInputBoxProps) {
  return (
    <div className="hifi-ask-input-container">
      <textarea
        className="hifi-ask-input"
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
      <button
        className="hifi-ask-send-btn"
        onClick={onSubmit}
        aria-label="发送问题"
        title="发送问题"
      >
        <ArrowUp size={16} />
      </button>
    </div>
  );
}
