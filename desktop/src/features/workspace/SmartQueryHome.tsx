import { AskInputBox } from "./smartQuery/AskInputBox";
import { SmartQueryHero } from "./smartQuery/SmartQueryHero";
import "./SmartQueryHome.css";

interface SmartQueryHomeProps {
  askInputValue: string;
  onAskInputChange: (value: string) => void;
  onSubmitAsk: () => void;
  projectId?: string;
}

export function SmartQueryHome({
  askInputValue,
  onAskInputChange,
  onSubmitAsk,
  projectId,
}: SmartQueryHomeProps) {
  return (
    <div className="smart-query-home">
      <div className="smart-query-home__content">
        <SmartQueryHero />

        <AskInputBox
          value={askInputValue}
          onChange={onAskInputChange}
          onSubmit={onSubmitAsk}
          projectId={projectId}
        />
      </div>
    </div>
  );
}
