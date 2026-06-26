import { AskContextDropZone } from "./smartQuery/AskContextDropZone";
import { AskInputBox } from "./smartQuery/AskInputBox";
import { SmartQueryHero } from "./smartQuery/SmartQueryHero";
import "./SmartQueryHome.css";

interface SmartQueryHomeProps {
  askInputValue: string;
  contextTables: string[];
  onAskInputChange: (value: string) => void;
  onSubmitAsk: () => void;
  onAddContextTable: (tableName: string) => void;
  onRemoveContextTable: (tableName: string) => void;
  onClearContextTables: () => void;
}

export function SmartQueryHome({
  askInputValue,
  contextTables,
  onAskInputChange,
  onSubmitAsk,
  onAddContextTable,
  onRemoveContextTable,
  onClearContextTables,
}: SmartQueryHomeProps) {
  return (
    <div className="smart-query-home">
      <div className="smart-query-home__content">
        <SmartQueryHero />

        <AskContextDropZone
          contextTables={contextTables}
          onAddContextTable={onAddContextTable}
          onRemoveContextTable={onRemoveContextTable}
          onClearContextTables={onClearContextTables}
        />

        <AskInputBox value={askInputValue} onChange={onAskInputChange} onSubmit={onSubmitAsk} />
      </div>
    </div>
  );
}
