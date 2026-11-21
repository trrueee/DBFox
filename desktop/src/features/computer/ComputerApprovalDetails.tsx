const ACTIONS: Record<string, string> = {
  click: "单击", double_click: "双击", type_text: "填写文字", key: "按键", scroll: "滚动画面",
  focus: "切换到目标窗口", navigate: "打开网页", back: "返回上一页", forward: "前进", reload: "刷新页面",
  new_tab: "打开新页面", select_tab: "切换页面", close_tab: "关闭页面",
};

export function ComputerApprovalDetails({ review }: { review: Record<string, unknown> }) {
  const action = typeof review.action === "string" ? review.action : "";
  const position = review.position && typeof review.position === "object" ? review.position as Record<string, unknown> : null;
  const x = position?.x;
  const y = position?.y;
  const point = typeof x === "number" && typeof y === "number" && Number.isFinite(x) && Number.isFinite(y)
    && x >= 0 && x <= 1 && y >= 0 && y <= 1 ? `X ${x} · Y ${y}（相对观察画面）` : "";
  const imageSize = typeof review.image_width === "number" && typeof review.image_height === "number"
    ? `${review.image_width} × ${review.image_height}` : "";
  const entries = [
    ["目标", review.target], ["动作", ACTIONS[action] ?? action], ["元素", review.element],
    ["画面落点", point], ["观察画面", imageSize], ["观察依据", review.observation_artifact_id],
    ["地址", review.url], ["输入文字", review.text], ["按键", review.key],
    ["观察时间", typeof review.observed_at === "number" ? new Date(review.observed_at).toLocaleString() : ""],
  ].filter((entry): entry is [string, string] => typeof entry[1] === "string" && Boolean(entry[1]));
  return <div className="grid gap-2 rounded-md border border-[var(--agent-border)] bg-[var(--agent-surface-muted)] p-3 text-sm">
    <dl className="m-0 grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-2">
      {entries.map(([label, value]) => <div key={label} className="contents"><dt className="text-[var(--agent-text-muted)]">{label}</dt>
        <dd className="m-0 whitespace-pre-wrap break-all text-[var(--agent-text)]">{value}</dd></div>)}
    </dl>
    <p className="m-0 text-xs text-[var(--agent-text-secondary)]">本次批准只执行这一个动作。敏感输入请人工接管。</p>
  </div>;
}
