import { describe, expect, it } from "vitest";
import {
  approvalStatusPresentation,
  completionLimitationLabel,
  databaseTypeLabel,
  datasourceStatusPresentation,
  runStatusPresentation,
  riskLevelLabel,
  safetyCheckLabel,
  userFacingErrorMessage,
} from "../presentation";

describe("user-facing presentation", () => {
  it("translates datasource and task states", () => {
    expect(datasourceStatusPresentation("needs_credentials").label).toBe("需要重新填写密码");
    expect(runStatusPresentation("waiting_approval").label).toBe("等待你的确认");
    expect(approvalStatusPresentation("expired").label).toBe("已失效");
    expect(databaseTypeLabel("postgres")).toBe("PostgreSQL");
    expect(safetyCheckLabel("blocked")).toBe("已拦截");
    expect(safetyCheckLabel("unknown")).toBe("等待检查");
    expect(riskLevelLabel("warning")).toBe("中风险");
    expect(completionLimitationLabel("TOOL_BUDGET_REACHED")).toBe("已达到工具调用上限");
  });

  it("maps technical errors to actionable Chinese messages", () => {
    expect(userFacingErrorMessage({ code: "CONNECTION_FAILED", message: "hidden" }))
      .toBe("数据库连接失败，请检查连接信息和网络。");
    expect(userFacingErrorMessage(new Error("Request could not be completed."), "连接测试未完成，请重试。"))
      .toBe("连接测试未完成，请重试。");
    expect(userFacingErrorMessage(new Error("Failed to fetch")))
      .toBe("无法连接 DBFox 服务，请确认应用已正常启动。");
  });

  it("keeps safe Chinese business messages", () => {
    expect(userFacingErrorMessage(new Error("连接名称不能为空"))).toBe("连接名称不能为空");
  });
});
