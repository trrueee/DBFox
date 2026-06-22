import type { CSSProperties } from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ChartArtifact } from "../../../../types/agentArtifact";
import { ChartArtifactView } from "../ChartArtifactView";

vi.mock("echarts-for-react", () => ({
  default: ({ style }: { style?: CSSProperties }) => <div data-testid="echarts-mock" style={style} />,
}));

describe("ChartArtifactView", () => {
  it("renders chart source field formulas", () => {
    const artifact: ChartArtifact = {
      id: "chart-1",
      type: "chart",
      title: "GMV 趋势图",
      chartType: "bar",
      series: [{ label: "2026-06-01", value: 120 }],
      sourceRefs: [
        { label: "GMV", formula: "SUM(orders.amount)", field: "orders.amount" },
        { label: "日期", formula: "DATE(orders.created_at)", field: "orders.created_at" },
      ],
    };

    render(<ChartArtifactView artifact={artifact} onToast={vi.fn()} />);

    expect(screen.getByText("GMV")).toBeTruthy();
    expect(screen.getByText("SUM(orders.amount)")).toBeTruthy();
    expect(screen.getByText("orders.amount")).toBeTruthy();
    expect(screen.getByText("日期")).toBeTruthy();
    expect(screen.getByText("DATE(orders.created_at)")).toBeTruthy();
  });
});
