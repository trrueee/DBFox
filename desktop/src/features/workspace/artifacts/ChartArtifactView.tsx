import { useMemo, useState } from "react";
import { Download } from "lucide-react";
import type { ChartArtifact } from "../../../types/agentArtifact";
import { downloadTextFile } from "./artifactActions";

export function ChartArtifactView({ artifact }: { artifact: ChartArtifact }) {
  const [viewType, setViewType] = useState<"line" | "bar">(artifact.chartType);
  const values = artifact.series.map((point) => point.value);
  const max = Math.max(...values, 1);
  const points = useMemo(() => artifact.series
    .map((point, index) => {
      const x = 30 + (index * 350) / Math.max(artifact.series.length - 1, 1);
      const y = 100 - (point.value / max) * 80;
      return `${x},${y}`;
    })
    .join(" "), [artifact.series, max]);

  const exportSvg = () => {
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 130"><polyline points="${points}" fill="none" stroke="#4F46E5" stroke-width="2.5" /></svg>`;
    downloadTextFile(`${artifact.id}.svg`, svg, "image/svg+xml;charset=utf-8");
  };

  return (
    <div className="hifi-ai-card mt-2">
      <div className="hifi-ai-card-header flex justify-between items-center">
        <span>{artifact.title}</span>
        <div className="flex items-center gap-1.5">
          <button className="hifi-guide-btn-secondary" style={{ height: "22px", fontSize: "9px" }} onClick={() => setViewType("line")}>折线</button>
          <button className="hifi-guide-btn-secondary" style={{ height: "22px", fontSize: "9px" }} onClick={() => setViewType("bar")}>柱状</button>
          <button className="hifi-guide-btn-secondary flex items-center gap-1" style={{ height: "22px", fontSize: "9px" }} onClick={exportSvg}><Download size={9} /> SVG</button>
        </div>
      </div>
      <div className="hifi-ai-card-body p-3">
        {artifact.description && <p className="text-[10px] text-slate-500 mb-2">{artifact.description}</p>}
        <svg viewBox="0 0 400 130" width="100%" height="112">
          <line x1="30" y1="20" x2="380" y2="20" stroke="#F1F5F9" strokeWidth="1" />
          <line x1="30" y1="50" x2="380" y2="50" stroke="#F1F5F9" strokeWidth="1" />
          <line x1="30" y1="80" x2="380" y2="80" stroke="#F1F5F9" strokeWidth="1" />
          <line x1="30" y1="100" x2="380" y2="100" stroke="#E2E8F0" strokeWidth="1.5" />
          <text x="4" y="23" fontSize="8" fill="#64748B">{max}</text>
          <text x="4" y="103" fontSize="8" fill="#64748B">0</text>
          {viewType === "line" ? (
            <>
              <polyline points={points} fill="none" stroke="#4F46E5" strokeWidth="2.5" />
              {artifact.series.map((point, index) => {
                const x = 30 + (index * 350) / Math.max(artifact.series.length - 1, 1);
                const y = 100 - (point.value / max) * 80;
                return <circle key={point.label} cx={x} cy={y} r="3" fill="#FFFFFF" stroke="#4F46E5" strokeWidth="1.5" />;
              })}
            </>
          ) : (
            artifact.series.map((point, index) => {
              const width = 22;
              const x = 25 + (index * 350) / Math.max(artifact.series.length - 1, 1);
              const height = (point.value / max) * 80;
              return <rect key={point.label} x={x} y={100 - height} width={width} height={height} rx="4" fill="#4F46E5" opacity="0.82" />;
            })
          )}
          {artifact.series.map((point, index) => {
            const x = 22 + (index * 350) / Math.max(artifact.series.length - 1, 1);
            return <text key={point.label} x={x} y="124" fontSize="7" fill="#64748B">{point.label}</text>;
          })}
        </svg>
      </div>
    </div>
  );
}
