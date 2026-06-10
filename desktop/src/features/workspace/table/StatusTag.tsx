export type TableStatus = "active" | "inactive" | "pending";

export function StatusTag({ value }: { value: TableStatus }) {
  return (
    <span className={`hifi-status-tag ${value}`}>
      <span className={`hifi-dot ${value}`} />
      {value}
    </span>
  );
}
