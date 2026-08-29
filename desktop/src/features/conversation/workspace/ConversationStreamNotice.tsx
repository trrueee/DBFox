import { CheckCircle2, RefreshCw, WifiOff } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "../../../components/ui/alert";
import { Button } from "../../../components/ui/button";
import { Spinner } from "../../../components/ui/spinner";
import type { ConversationStreamState } from "../conversationStreamRuntime";

export function ConversationStreamNotice({
  state,
  error,
  onRefresh,
}: {
  state: ConversationStreamState;
  error?: string | null;
  onRefresh?: () => Promise<unknown> | void;
}) {
  if (state === "reconnecting" || state === "recovering_snapshot") {
    return (
      <div className="conv-stream-notice">
        <Alert role="status" aria-live="polite">
          <Spinner role="presentation" aria-hidden="true" aria-label={undefined} />
          <AlertTitle>{state === "recovering_snapshot" ? "正在读取最新状态" : "正在恢复实时连接"}</AlertTitle>
          <AlertDescription>
            {state === "recovering_snapshot"
              ? "实时历史游标已失效；DBFox 正在读取耐久快照，不会重放写操作。"
              : "已显示内容可能暂时不是最新；DBFox 正在从耐久快照恢复，不会重放写操作。"}
          </AlertDescription>
        </Alert>
      </div>
    );
  }
  if (state === "recovered") {
    return (
      <div className="conv-stream-notice">
        <Alert role="status" aria-live="polite">
          <CheckCircle2 aria-hidden="true" />
          <AlertTitle>已恢复最新状态</AlertTitle>
          <AlertDescription>当前内容已与耐久快照同步；后续更新继续通过实时连接接收。</AlertDescription>
        </Alert>
      </div>
    );
  }
  if (state !== "failed" && !error) return null;
  return (
    <div className="conv-stream-notice">
      <Alert variant="destructive">
        <WifiOff aria-hidden="true" />
        <AlertTitle>实时连接已中断</AlertTitle>
        <AlertDescription>
          <span>{error || "无法继续接收任务更新，请读取最新状态。"}</span>
          {onRefresh ? (
            <Button type="button" size="sm" variant="outline" onClick={() => void onRefresh()}>
              <RefreshCw aria-hidden="true" />
              刷新最新状态
            </Button>
          ) : null}
        </AlertDescription>
      </Alert>
    </div>
  );
}
