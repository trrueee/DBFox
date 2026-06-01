export function TextBlock({ content }: { content: string }) {
  return (
    <div style={{ padding: 8, background: "var(--bg-secondary)", lineHeight: 1.55 }}>
      {content}
    </div>
  );
}
