import type { TableArtifact } from "../../../types/agentArtifact";

export function TableArtifactView({ artifact }: { artifact: TableArtifact }) {
  return (
    <div className="hifi-ai-card">
      <div className="hifi-ai-card-header">{artifact.title}</div>
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
      </div>
    </div>
  );
}
