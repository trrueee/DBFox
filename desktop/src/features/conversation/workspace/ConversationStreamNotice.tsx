import {
  CheckCircleIcon,
  ArrowsClockwiseIcon,
  WifiSlashIcon,
} from "@/components/icons";

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
        <div className="conv-stream-status" role="status">
          <Spinner role="presentation" aria-hidden="true" aria-label={undefined} />
          <span>{state === "recovering_snapshot" ? "正在读取最新状态" : "正在恢复实时连接"}</span>
          <span className="conv-stream-status__detail">任务状态以同步结果为准</span>
        </div>
      </div>
    );
  }
  if (state === "recovered") {
    return (
      <div className="conv-stream-notice">
        <div className="conv-stream-status" role="status">
          <CheckCircleIcon aria-hidden="true" />
          <span>已恢复最新状态</span>
        </div>
      </div>
    );
  }
  if (state !== "failed" && !error) return null;
  return (
    <div className="conv-stream-notice">
      <div className="conv-stream-status" role="status">
        <WifiSlashIcon aria-hidden="true" />
        <span>实时连接已中断</span>
        <span className="conv-stream-status__detail">任务可能仍在运行</span>
          {onRefresh ? (
            <Button type="button" size="sm" variant="ghost" onClick={() => void Promise.resolve(onRefresh()).catch(() => undefined)}>
              <ArrowsClockwiseIcon aria-hidden="true" />
              刷新最新状态
            </Button>
          ) : null}
        {error ? <details className="conv-stream-status__error"><summary>详情</summary><p>{error}</p></details> : null}
      </div>
    </div>
  );
}
