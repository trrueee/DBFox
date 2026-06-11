import { Activity, AlertTriangle, CheckCircle2, MinusCircle, TrendingUp } from "lucide-react";
import type { MetricArtifact } from "../../../types/agentArtifact";

interface MetricArtifactViewProps {
  artifact: MetricArtifact;
}

const TONE_CLASS: Record<NonNullable<MetricArtifact["cards"][number]["tone"]>, string> = {
  neutral: "border-slate-200 bg-slate-50 text-slate-700",
  good: "border-emerald-200 bg-emerald-50 text-emerald-800",
  warn: "border-amber-200 bg-amber-50 text-amber-900",
  danger: "border-red-200 bg-red-50 text-red-800",
};

const TONE_ICON = {
  neutral: MinusCircle,
  good: CheckCircle2,
  warn: AlertTriangle,
  danger: AlertTriangle,
};

export function MetricArtifactView({ artifact }: MetricArtifactViewProps) {
  return (
    <div className="hifi-ai-card mt-2">
      <div className="hifi-ai-card-header flex justify-between items-center">
        <span className="flex items-center gap-1.5"><Activity size={12} />{artifact.title}</span>
        <span className="text-[9px] text-slate-400">analysis summary</span>
      </div>
      <div className="hifi-ai-card-body p-3">
        {artifact.description && <p className="text-[10px] text-slate-500 mb-2">{artifact.description}</p>}
        <div className="grid grid-cols-2 xl:grid-cols-4 gap-2">
          {artifact.cards.map((card) => {
            const tone = card.tone || "neutral";
            const Icon = TONE_ICON[tone] || TrendingUp;
            return (
              <div key={`${card.label}-${card.value}`} className={`rounded-lg border p-2.5 ${TONE_CLASS[tone]}`}>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[10px] font-semibold opacity-80">{card.label}</span>
                  <Icon size={12} />
                </div>
                <div className="text-[17px] font-bold leading-tight text-slate-950">{card.value}</div>
                {card.helper && <div className="text-[9px] leading-snug opacity-75 mt-1">{card.helper}</div>}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
