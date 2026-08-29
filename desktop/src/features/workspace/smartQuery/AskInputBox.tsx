import { UnifiedComposer } from "../../../components/agent/UnifiedComposer";
import type { WorkbenchReference } from "../../../types/workspace";

interface AskInputBoxProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  projectId?: string;
  references?: readonly WorkbenchReference[];
  onRemoveReference?: (reference: WorkbenchReference) => void;
}

export function AskInputBox({
  value,
  onChange,
  onSubmit,
  references,
  onRemoveReference,
}: AskInputBoxProps) {
  return (
    <UnifiedComposer
      value={value}
      onChange={onChange}
      onSubmit={onSubmit}
      placeholder="让 DBFox 分析、创建、修改或研究任何事情…"
      ariaLabel="新任务"
      references={references}
      onRemoveReference={onRemoveReference}
      autoFocus
    />
  );
}
