import { AskInputBox } from "./smartQuery/AskInputBox";
import { SmartQueryHero } from "./smartQuery/SmartQueryHero";
import "./SmartQueryHome.css";
import type { WorkbenchReference } from "../../../../sdk/frontend/index";

interface SmartQueryHomeProps {
  askInputValue: string;
  onAskInputChange: (value: string) => void;
  onSubmitAsk: () => void;
  projectId?: string;
  reference?: WorkbenchReference | null;
  onClearReference?: () => void;
}

export function SmartQueryHome({
  askInputValue,
  onAskInputChange,
  onSubmitAsk,
  projectId,
  reference,
  onClearReference,
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
          reference={reference}
          onClearReference={onClearReference}
        />
      </div>
    </div>
  );
}
