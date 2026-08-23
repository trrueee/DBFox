import { AskInputBox } from "./smartQuery/AskInputBox";
import { SmartQueryHero } from "./smartQuery/SmartQueryHero";
import "./SmartQueryHome.css";
import type { RequestedResourceRef } from "../../lib/api/generated/types.gen";

interface SmartQueryHomeProps {
  askInputValue: string;
  onAskInputChange: (value: string) => void;
  onSubmitAsk: () => void;
  projectId: string;
  resourceIntents: readonly RequestedResourceRef[];
  onResourceIntentsChange: (next: RequestedResourceRef[]) => void;
}

export function SmartQueryHome({
  askInputValue,
  onAskInputChange,
  onSubmitAsk,
  projectId,
  resourceIntents,
  onResourceIntentsChange,
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
          resourceIntents={resourceIntents}
          onResourceIntentsChange={onResourceIntentsChange}
        />
      </div>
    </div>
  );
}
