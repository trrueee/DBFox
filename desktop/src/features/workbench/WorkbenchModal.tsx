import type { ReactNode } from "react";
import { X } from "lucide-react";

interface WorkbenchModalProps {
  title: string;
  children: ReactNode;
  onClose: () => void;
}

export function WorkbenchModal({ title, children, onClose }: WorkbenchModalProps) {
  return (
    <div className="wb-modal-backdrop">
      <div className="wb-modal-panel">
        <header className="wb-modal-header">
          <span>{title}</span>
          <button className="wb-icon-button" type="button" onClick={onClose} title="关闭">
            <X size={16} />
          </button>
        </header>
        <div className="wb-modal-body">{children}</div>
      </div>
    </div>
  );
}
