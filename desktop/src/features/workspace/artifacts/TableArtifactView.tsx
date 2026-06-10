import { Copy, Download } from "lucide-react";
import type { TableArtifact } from "../../../types/agentArtifact";
import { copyText, downloadTextFile, toCsv } from "./artifactActions";

export function TableArtifactView({ artifact }: { artifact: TableArtifact }) {
  const csv = toCsv(artifact.columns, artifact.rows);

  return (
    <div className="hifi-ai-card">
      <div className="hifi-ai-card-header flex items-center justify-between gap-2">
        <span>{artifact.title}</span>
        <span className="hifi-guide-chip-prod">TABLE</span>
      </div>
      <div className="hifi-ai-card-body p-3">
        {artifact.description && <p className="text-[10px] text-slate-500 mb-2">{artifact.description}</p>}
        <table className="hifi-table">
          <thead>
            <tr>{artifact.columns.map((column) => <th key={column}>{column}</th>)}</tr>
          </thead>
          <tbody>
            {artifact.rows.map((row, rowIndex) => (
              <tr key={rowIndex}>{row.map((cell, cellIndex) => <td key={`${rowIndex}-${cellIndex}`}>{cell}</td>)}</tr>
            ))}
          </tbody>
        </table>
        <div className="flex gap-2 justify-end mt-3">
          <button className="hifi-guide-btn-secondary flex items-center gap-1" style={{ height: "24px", fontSize: "10px" }} onClick={() => copyText(csv)}>
            <Copy size={10} />
            复制 CSV
          </button>
          <button className="hifi-guide-btn-secondary flex items-center gap-1" style={{ height: "24px", fontSize: "10px" }} onClick={() => downloadTextFile(`${artifact.id}.csv`, csv, "text/csv;charset=utf-8")}>
            <Download size={10} />
            导出 CSV
          </button>
        </div>
      </div>
    </div>
  );
}
