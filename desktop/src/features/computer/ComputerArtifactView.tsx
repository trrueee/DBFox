import { useQuery } from "@tanstack/react-query";
import { Button, ErrorState, LoadingState } from "../../components/ui";
import { getUserErrorMessage } from "../../lib/api/client";
import { COMPUTER_REPRESENTATION } from "../../lib/api/computer";
import type { ArtifactEnvelope, ArtifactViewContext } from "../workspace/artifacts/types";
import { asRecord } from "../workspace/artifacts/types";
import { CaptureImage } from "./CaptureImage";
import "./computer.css";

export function ComputerArtifactView({ artifact, context }: { artifact: ArtifactEnvelope<unknown>; context: ArtifactViewContext }) {
  const payload = asRecord(artifact.payload);
  const isImage = context.representations.available.some(item => item.representation_type === COMPUTER_REPRESENTATION
    && item.operations.some(operation => operation.purpose === "model_media"));
  const image = useQuery({ queryKey: ["computer-evidence-image", artifact.id], retry: false, staleTime: Infinity, gcTime: 0, enabled: isImage,
    queryFn: ({ signal }) => context.representations.stream(artifact.id, COMPUTER_REPRESENTATION, { operation: "image" }, signal) });
  const timestamp = typeof payload.observed_at === "number" ? payload.observed_at : typeof payload.performed_at === "number" ? payload.performed_at : null;
  return <section className="computer-dock" aria-label={isImage ? "电脑观察证据" : "电脑操作证据"}>
    <header className="computer-header"><div><h2>{isImage ? "实际画面观察" : "操作记录"}</h2>
      <p>{timestamp ? new Date(timestamp).toLocaleString() : ""} · 此记录保留操作事实，任务结果需单独核实</p></div></header>
    {isImage ? image.isPending ? <LoadingState label="正在读取截图证据" /> : image.isError ? <ErrorState title="截图证据不可用"
      description={getUserErrorMessage(image.error, "截图已过期或不再可读。")} onRetry={() => void image.refetch()} /> : image.data ? <CaptureImage image={image.data} alt={`${artifact.title}的实际观察画面`} /> : null
      : <p>{typeof payload.summary === "string" ? payload.summary : "已记录一次电脑操作。"}</p>}
    {typeof payload.url === "string" && <p className="computer-hint">{payload.url}</p>}
    {context.openArtifact && <div className="computer-actions">{artifact.relations?.filter(item => item.relation === "supports").map(item => {
      const related = context.resolveArtifact?.(item.artifact_id) ?? { id: item.artifact_id, type: "dbfox.computer.observation", title: "操作后画面" };
      return <Button key={item.artifact_id} variant="outline" size="sm" onClick={() => context.openArtifact?.(related)}>查看操作后画面</Button>;
    })}</div>}
    <p className="computer-footnote">截图最多保留 24 小时，并受本机存储预算限制。</p>
  </section>;
}
