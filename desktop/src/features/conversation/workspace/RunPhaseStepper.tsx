import { PHASE_LABELS, PHASE_ORDER, type TimelineStage } from "./runTraceModel";

export function RunPhaseStepper({ stages }: { stages: TimelineStage[] }) {
  const byPhase = new Map(stages.map((stage) => [stage.phase, stage]));

  return (
    <div className="conv-phase-stepper" aria-label="Agent execution phases">
      {PHASE_ORDER.map((phase) => {
        const status = byPhase.get(phase)?.status ?? "idle";
        return (
          <span
            key={phase}
            className={`conv-phase-dot is-${status}`}
            title={PHASE_LABELS[phase]}
            aria-label={`${PHASE_LABELS[phase]} ${status}`}
          />
        );
      })}
    </div>
  );
}
