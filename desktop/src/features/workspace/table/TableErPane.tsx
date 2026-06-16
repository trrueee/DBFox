import { Maximize2, ZoomIn, ZoomOut } from "lucide-react";

export function TableErPane({ tableId }: { tableId: string }) {
  return (
    <div className="h-full w-full bg-[var(--color-bg)] relative overflow-hidden flex flex-col p-4">
      <span className="text-[10px] text-[var(--color-text-muted)] block mb-2">ER 关系图 &gt; {tableId}</span>
      <div className="flex-1 relative border border-[var(--color-border)] bg-[var(--color-panel)] rounded-xl shadow-inner overflow-hidden">
        {/* Active Table Node */}
        <div className="absolute bg-[var(--color-panel)] border border-[var(--color-border)] rounded shadow-sm text-[8px] z-10 w-[95px]" style={{ left: "20px", top: "20px" }}>
          <div className="bg-[var(--color-primary-soft)] border-b border-[var(--color-border)] px-1.5 py-0.5 font-bold flex justify-between text-[var(--color-text-primary)]">
            <span>{tableId}</span>
          </div>
          <div className="p-1 leading-normal text-[var(--color-text-secondary)] font-mono">
            <div><strong className="text-[var(--color-text-primary)]">id</strong> (PK)</div>
            <div>tenant_id</div>
            <div>status</div>
            <div>created_at</div>
          </div>
        </div>
        {/* Linked Table Node */}
        <div className="absolute bg-[var(--color-panel)] border border-[var(--color-border)] rounded shadow-sm text-[8px] z-10 w-[95px]" style={{ left: "180px", top: "20px" }}>
          <div className="bg-[var(--color-warning-soft)] border-b border-[var(--color-border)] px-1.5 py-0.5 font-bold flex justify-between text-[var(--color-text-primary)]">
            <span>id_users</span>
          </div>
          <div className="p-1 leading-normal text-[var(--color-text-secondary)] font-mono">
            <div><strong className="text-[var(--color-text-primary)]">id</strong> (PK)</div>
            <div>tenant_id</div>
            <div>account</div>
          </div>
        </div>
        {/* Relationship Link */}
        <svg className="absolute inset-0 w-full h-full pointer-events-none">
          <path d="M115 65 C 145 65, 150 65, 180 65" stroke="var(--color-border)" strokeWidth="1.5" fill="none" strokeDasharray="4 2" />
        </svg>
        {/* Zoom controls */}
        <div className="hifi-er-zoom-controls">
          <div className="hifi-er-zoom-btn"><ZoomIn size={12} /></div>
          <div className="hifi-er-zoom-btn"><ZoomOut size={12} /></div>
          <div className="hifi-er-zoom-btn"><Maximize2 size={12} /></div>
        </div>
      </div>
    </div>
  );
}
