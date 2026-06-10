import { Sparkles } from "lucide-react";

export function EmptyArtifactsState() {
  return (
    <div className="hifi-ai-card mt-2">
      <div className="hifi-ai-card-header flex items-center gap-1.5">
        <Sparkles size={12} className="text-purple-500" />
        <span>等待 Agent 产物</span>
      </div>
      <div className="hifi-ai-card-body p-4 text-[10px] leading-relaxed text-slate-500">
        当前会话还没有返回 artifacts。前端不会再使用 mock 结果兜底；后端返回 chart、sql、table 或 markdown 类型产物后，会在这里自动渲染。
      </div>
    </div>
  );
}
