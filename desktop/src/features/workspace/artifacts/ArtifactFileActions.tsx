import { useEffect, useRef, useState } from "react";
import { Button } from "../../../components/ui";
import { agentApi } from "../../../lib/api/agent";
import { getUserErrorMessage } from "../../../lib/api/client";
import { downloadBlobFile } from "./artifactActions";
import type { ArtifactFile } from "./artifactViewRegistry";
import type { ArtifactEnvelope } from "./types";

const imageTypes = new Set(["image/png", "image/jpeg", "image/gif", "image/webp"]);
const textTypes = new Set(["text/plain", "text/markdown", "text/csv", "application/json"]);

type Preview = { fileName: string } & ({ imageUrl: string } | { text: string });

function imageDataUrl(blob: Blob): Promise<string> {
  // Packaged Electron permits data images under its existing CSP.
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === "string") resolve(reader.result);
      else reject(new Error("无法预览工件图片。"));
    };
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
}

export function ArtifactFileActions({ artifact, files, onToast }: {
  artifact: ArtifactEnvelope<unknown>;
  files: readonly ArtifactFile[];
  onToast: (message: string) => void;
}) {
  const pending = useRef<AbortController | null>(null);
  const [loading, setLoading] = useState(false);
  const [preview, setPreview] = useState<Preview | null>(null);

  useEffect(() => () => pending.current?.abort(), []);

  async function openFile(file: ArtifactFile, mode: "preview" | "download") {
    if (pending.current) return;
    const controller = new AbortController();
    const image = imageTypes.has(file.mediaType);
    const limit = mode === "preview" ? (image ? 4 * 1024 * 1024 : 128 * 1024) : undefined;
    pending.current = controller;
    setLoading(true);
    try {
      const { blob, fileName = artifact.title } = await agentApi.fetchArtifactFile(
        artifact.id, file.representationType, { operation: file.operation },
        controller.signal, artifact.session_id, limit,
      );
      if (controller.signal.aborted) return;
      if (mode === "download") {
        if (!downloadBlobFile(fileName, blob)) onToast("无法下载工件文件。");
        return;
      }
      if (blob.type.split(";")[0] !== file.mediaType) throw new Error("文件内容类型与工件声明不一致。");
      if (image) {
        const imageUrl = await imageDataUrl(blob);
        if (!controller.signal.aborted) setPreview({ fileName, imageUrl });
      } else {
        const content = await blob.text();
        if (!controller.signal.aborted) setPreview({ fileName, text: content });
      }
    } catch (error) {
      if (!controller.signal.aborted) onToast(getUserErrorMessage(error, "无法读取工件文件。"));
    } finally {
      pending.current = null;
      if (!controller.signal.aborted) setLoading(false);
    }
  }

  return (
    <div className="artifact-file-actions" aria-busy={loading}>
      {files.map((file) => (
        <div className="artifact-file-action-row" key={`${file.representationType}:${file.operation}`}>
          <span title={file.operation}>{file.mediaType}</span>
          {(imageTypes.has(file.mediaType) || textTypes.has(file.mediaType)) && (
            <Button variant="ghost" size="sm" aria-label={`预览 ${file.mediaType}`} disabled={loading} onClick={() => void openFile(file, "preview")}>
              预览
            </Button>
          )}
          <Button variant="secondary" size="sm" aria-label={`下载 ${file.mediaType}`} disabled={loading} onClick={() => void openFile(file, "download")}>
            下载
          </Button>
        </div>
      ))}
      {preview && (
        <div className="artifact-file-preview" aria-label={preview.fileName}>
          {"imageUrl" in preview ? <img src={preview.imageUrl} alt={preview.fileName} /> : <pre>{preview.text}</pre>}
        </div>
      )}
    </div>
  );
}
