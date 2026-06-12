import { useEffect, useRef, useState } from "react";
import { Loader2, Brain } from "lucide-react";

interface ThinkingStepProps {
  content: string;
  status: "idle" | "running" | "info";
  /** When true, the step is the latest active one and shows cursor animation. */
  isLatest?: boolean;
}

export function ThinkingStep({ content, status, isLatest = false }: ThinkingStepProps) {
  const isActive = status === "running" && isLatest;
  const [visibleLength, setVisibleLength] = useState(isActive ? 0 : content.length);
  const rafRef = useRef<number>(0);

  // Streaming reveal: gradually reveal text when active
  useEffect(() => {
    if (!isActive) {
      setVisibleLength(content.length);
      return;
    }

    let current = 0;
    const target = content.length;
    const stepPerFrame = Math.max(1, Math.ceil(target / 40)); // reveal over ~40 frames

    const reveal = () => {
      current = Math.min(current + stepPerFrame, target);
      setVisibleLength(current);
      if (current < target) {
        rafRef.current = requestAnimationFrame(reveal);
      }
    };
    rafRef.current = requestAnimationFrame(reveal);

    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [isActive, content]);

  if (!content && !isActive) {
    return null;
  }

  const visibleText = content.slice(0, visibleLength);
  const showCursor = isActive && visibleLength < content.length;

  return (
    <div className={`task-thinking-step ${isActive ? "task-thinking-active" : ""}`}>
      <div className="task-thinking-dot">
        {isActive ? (
          <Loader2 size={11} className="animate-spin text-indigo-500" />
        ) : (
          <Brain size={11} className="text-slate-400" />
        )}
      </div>
      <div className="task-thinking-card">
        <div className="task-thinking-text">
          {visibleText || (isActive ? "思考中…" : "")}
          {showCursor && <span className="task-thinking-cursor" />}
        </div>
      </div>
    </div>
  );
}
