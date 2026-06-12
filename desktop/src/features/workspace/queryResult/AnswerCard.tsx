import { Bot, Lightbulb, AlertTriangle, CheckCircle2, FileText } from "lucide-react";
import type { AgentAnswer } from "../../../lib/api/types";
import { MarkdownContent } from "./MarkdownContent";

interface AnswerCardProps {
  answer: AgentAnswer;
}

const BOILERPLATE = new Set([
  "i do not have a successful result set to analyze yet.",
  "the query returned no rows",
  "i could not complete the analysis",
]);

function isRealAnswer(answer: AgentAnswer): boolean {
  const text = (answer.answer || "").trim().toLowerCase();
  if (!text) return false;
  if (BOILERPLATE.has(text)) return false;
  return true;
}

export function AnswerCard({ answer }: AnswerCardProps) {
  const hasFindings = answer.key_findings && answer.key_findings.length > 0;
  const hasCaveats = answer.caveats && answer.caveats.length > 0;
  const hasEvidence = answer.evidence && answer.evidence.length > 0;

  if (!isRealAnswer(answer) && !hasFindings && !hasCaveats) return null;

  return (
    <div className="hifi-answer-card">
      <div className="hifi-answer-card-head">
        <span className="hifi-answer-avatar">
          <Bot size={13} />
        </span>
        <span>AI</span>
      </div>

      {/* Main answer text */}
      {answer.answer && (
        <MarkdownContent content={answer.answer} className="hifi-answer-text" />
      )}

      {/* Key findings */}
      {hasFindings && (
        <div className="hifi-answer-findings">
          <div className="hifi-answer-section-title">
            <Lightbulb size={12} />
            <span>关键发现</span>
          </div>
          <ul>
            {answer.key_findings.map((finding, i) => (
              <li key={i}>
                <CheckCircle2 size={11} />
                <span>{finding}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Evidence */}
      {hasEvidence && (
        <div className="hifi-answer-evidence">
          <div className="hifi-answer-section-title">
            <FileText size={12} />
            <span>数据依据</span>
          </div>
          <ul>
            {answer.evidence.map((ev, i) => (
              <li key={i}>
                <span className="hifi-evidence-label">{ev.label}</span>
                {ev.value != null && (
                  <span className="hifi-evidence-value">{String(ev.value)}</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Caveats */}
      {hasCaveats && (
        <div className="hifi-answer-caveats">
          <div className="hifi-answer-section-title">
            <AlertTriangle size={12} />
            <span>注意事项</span>
          </div>
          <ul>
            {answer.caveats.map((caveat, i) => (
              <li key={i}>{caveat}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
