import { AlertTriangle, CheckCircle2, Circle, Loader2, XCircle } from "lucide-react";
import type { TraceArtifact } from "../../../types/agentArtifact";

interface TraceArtifactViewProps {
  artifact: TraceArtifact;
}

const STATUS_META: Record<TraceArtifact["stages"][number]["status"], { label: string; className: string; icon: typeof Circle }> = {
  success: { label: "完成", className: "text-emerald-600 bg-emerald-50 border-emerald-200", icon: CheckCircle2 },
  running: { label: "进行中", className: "text-blue-600 bg-blue-50 border-blue-200", icon: Loader2 },
  warning: { label: "需关注", className: "text-amber-700 bg-amber-50 border-amber-200", icon: AlertTriangle },
  failed: { label: "失败", className: "text-red-700 bg-red-50 border-red-200", icon: XCircle },
  skipped: { label: "跳过", className: "text-slate-500 bg-slate-50 border-slate-200", icon: Circle },
};

export function TraceArtifactView({ artifact }: TraceArtifactViewProps) {
  return (
    <div className="hifi-ai-card mt-2">
      <div className="hifi-ai-card-header flex justify-between items-center">
        <span>{artifact.title}</span>
        <span className="text-[9px] text-slate-400">trace</span>
      </div>
      <div className="hifi-ai-card-body p-3">
        {artifact.description && <p className="text-[10px] text-slate-500 mb-3">{artifact.description}</p>}
        <div className="flex flex-col gap-2">
          {artifact.stages.map((stage, index) => {
            const meta = STATUS_META[stage.status] || STATUS_META.skipped;
            const Icon = meta.icon;
            return (
              <div key={`${stage.label}-${index}`} className="flex gap-2">
                <div className="flex flex-col items-center">
                  <span className={`w-5 h-5 rounded-full border flex items-center justify-center ${meta.className}`}>
                    <Icon size={11} className={stage.status === "running" ? "animate-spin" : ""} />
                  </span>
                  {index < artifact.stages.length - 1 && <span className="w-px flex-1 min-h-[16px] bg-slate-200" />}
                </div>
                <div className="min-w-0 pb-2 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-[11px] font-semibold text-slate-800">{stage.label}</span>
                    <span className={`text-[8px] border rounded-full px-1.5 py-0.5 ${meta.className}`}>{meta.label}</span>
                  </div>
                  {stage.detail && <div className="text-[10px] text-slate-500 leading-relaxed mt-0.5 whitespace-pre-wrap">{stage.detail}</div>}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
