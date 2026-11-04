import { ArrowUpRight, X } from "lucide-react";
import { ResourceIcon, resourceLabel, type ResourceKind } from "./resourcePresentation";
import "./resources.css";

/** Shared presentation only. Resource identity and authority stay with the caller. */
export function ReferenceCard({ name, kind = "resource", description, onOpen, onRemove, compact = false }: {
  name: string; kind?: ResourceKind; description?: string; onOpen?: () => void; onRemove?: () => void; compact?: boolean;
}) {
  const content = <>
    <span className="resource-reference__icon"><ResourceIcon name={name} kind={kind} size={compact ? 16 : 20} /></span>
    <span className="resource-reference__copy"><span className="resource-reference__name">{name}</span>
      {!compact ? <span className="resource-reference__detail">{description ?? resourceLabel(kind)}</span> : null}</span>
    {onOpen ? <ArrowUpRight className="resource-reference__open" size={14} aria-hidden="true" /> : null}
  </>;
  return <span className={`resource-reference${compact ? " resource-reference--compact" : ""}`}>
    {onOpen ? <button type="button" className="resource-reference__main" title={name} aria-label={name} aria-description={description ?? resourceLabel(kind)} onClick={(event) => { event.stopPropagation(); onOpen(); }}>{content}</button>
      : <span className="resource-reference__main" title={name}>{content}</span>}
    {onRemove ? <button type="button" className="resource-reference__remove" aria-label={`移除上下文：${name}`} onClick={(event) => { event.stopPropagation(); onRemove(); }}><X size={14} aria-hidden="true" /></button> : null}
  </span>;
}
