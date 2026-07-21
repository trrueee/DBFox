import { useEffect, useMemo, useState } from "react";

interface SmoothedStreamingState {
  identity: string;
  displayed: string;
  streamWasActive: boolean;
}

export function useSmoothedStreamingText(targetText: string, active: boolean, identity: string) {
  const reducedMotion = usePrefersReducedMotion();
  const [state, setState] = useState<SmoothedStreamingState>(() => ({
    identity,
    displayed: active && targetText && !reducedMotion ? "" : targetText,
    streamWasActive: active,
  }));
  let renderState = state;
  const applyRenderState = (nextState: SmoothedStreamingState) => {
    renderState = nextState;
    setState(nextState);
  };
  if (renderState.identity !== identity) {
    applyRenderState({ identity, displayed: active && targetText && !reducedMotion ? "" : targetText, streamWasActive: active });
  } else if (active && !renderState.streamWasActive) {
    applyRenderState({ ...renderState, streamWasActive: true });
  } else if ((reducedMotion || !renderState.streamWasActive) && renderState.displayed !== targetText) {
    applyRenderState({ ...renderState, displayed: targetText, streamWasActive: active });
  } else if (renderState.streamWasActive && renderState.displayed
    && (!targetText.startsWith(renderState.displayed) || renderState.displayed.length > targetText.length)) {
    applyRenderState({ ...renderState, displayed: targetText, streamWasActive: active });
  } else if (!active && renderState.streamWasActive && renderState.displayed === targetText) {
    applyRenderState({ ...renderState, streamWasActive: false });
  }

  useEffect(() => {
    if (reducedMotion || !renderState.streamWasActive || renderState.displayed === targetText) return;
    if (!targetText.startsWith(renderState.displayed) || renderState.displayed.length > targetText.length) return;
    const timer = window.setTimeout(() => {
      setState((current) => {
        if (current.identity !== identity || reducedMotion || !current.streamWasActive) return current;
        if (!targetText.startsWith(current.displayed) || current.displayed.length > targetText.length) {
          return { ...current, displayed: targetText, streamWasActive: active };
        }
        const remaining = targetText.slice(current.displayed.length);
        const nextText = targetText.slice(0, current.displayed.length + revealCount(remaining));
        return { ...current, displayed: nextText, streamWasActive: active || nextText.length < targetText.length };
      });
    }, revealDelay(renderState.displayed));
    return () => window.clearTimeout(timer);
  }, [active, identity, reducedMotion, renderState.displayed, renderState.streamWasActive, targetText]);

  return useMemo(() => ({
    text: renderState.displayed,
    isRevealing: renderState.streamWasActive && renderState.displayed.length < targetText.length,
  }), [renderState.displayed, renderState.streamWasActive, targetText]);
}

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(() =>
    typeof window !== "undefined" && typeof window.matchMedia === "function"
      ? window.matchMedia("(prefers-reduced-motion: reduce)").matches : false);
  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return;
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const onChange = () => setReduced(media.matches);
    onChange();
    media.addEventListener?.("change", onChange);
    return () => media.removeEventListener?.("change", onChange);
  }, []);
  return reduced;
}

function revealCount(remaining: string): number {
  if (!remaining) return 0;
  const leadingWhitespace = remaining.match(/^\s+/)?.[0].length || 0;
  const backlog = remaining.length;
  const base = backlog > 240 ? 42 : backlog > 120 ? 26 : backlog > 60 ? 14 : backlog > 24 ? 8 : 4;
  const budget = Math.min(Math.max(base, leadingWhitespace + 2), remaining.length);
  const punctuation = remaining.slice(0, budget).search(/[。！？!?；;，,、\n]/);
  return punctuation >= 1 ? punctuation + 1 : budget;
}

function revealDelay(displayed: string): number {
  const last = displayed.at(-1);
  if (!last) return 12;
  if (last === "\n") return 70;
  if (/[。！？!?；;]/.test(last)) return 90;
  if (/[，,、]/.test(last)) return 54;
  return 24;
}
