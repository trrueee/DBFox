import { describe, expect, it } from "vitest";
import type { ConversationArtifact } from "../../../../types/conversation";
import { toChartArtifactModel } from "../conversationArtifactModels";

describe("conversationArtifactModels", () => {
  it("promotes enriched chart payload fields to the chart artifact model", () => {
    const artifact: ConversationArtifact = {
      id: "chart-1",
      conversation_id: "conv-1",
      run_id: "run-1",
      message_id: "msg-1",
      semantic_id: "chart_suggestion",
      type: "chart",
      title: "GMV 趋势",
      status: "completed",
      sequence: 1,
      payload: {
        type: "line",
        unit: "CNY",
        x_label: "日期",
        y_label: "GMV",
        series_label: "GMV",
        data_label: true,
        sample_size: 128,
        series: [{ label: "2026-06-01", value: 120 }],
        source_refs: [{ label: "GMV", formula: "SUM(amount)", field: "orders.amount" }],
      },
      presentation: {},
      depends_on: [],
      refs: {},
      created_at: null,
    };

    const model = toChartArtifactModel(artifact);

    expect(model.unit).toBe("CNY");
    expect(model.xLabel).toBe("日期");
    expect(model.yLabel).toBe("GMV");
    expect(model.seriesLabel).toBe("GMV");
    expect(model.dataLabel).toBe(true);
    expect(model.sampleSize).toBe(128);
    expect(model.sourceRefs).toEqual([{ label: "GMV", formula: "SUM(amount)", field: "orders.amount" }]);
  });
});
