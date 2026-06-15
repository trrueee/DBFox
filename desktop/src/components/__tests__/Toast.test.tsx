import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { describe, expect, it } from "vitest";
import { ToastProvider, useToast } from "../Toast";

function TestComponent({ msg, type = "info" }: { msg: string; type?: "success" | "error" | "warning" | "info" }) {
  const { toast } = useToast();
  return <button onClick={() => toast(msg, type)}>Trigger Toast</button>;
}

describe("ToastProvider and useToast", () => {
  it("renders success and error toasts with correct live-region and role attributes", async () => {
    render(
      <ToastProvider>
        <div data-testid="triggers">
          <TestComponent msg="Success message" type="success" />
          <TestComponent msg="Error message" type="error" />
        </div>
      </ToastProvider>
    );

    const triggerButtons = screen.getAllByText("Trigger Toast");
    
    // Trigger success toast
    triggerButtons[0].click();
    
    const successToast = await screen.findByText("Success message");
    expect(successToast).toBeInTheDocument();
    
    const successContainer = successToast.closest("[role]");
    expect(successContainer).toHaveAttribute("role", "status");
    expect(successContainer).toHaveAttribute("aria-live", "polite");

    // Trigger error toast
    triggerButtons[1].click();

    const errorToast = await screen.findByText("Error message");
    expect(errorToast).toBeInTheDocument();
    
    const errorContainer = errorToast.closest("[role]");
    expect(errorContainer).toHaveAttribute("role", "alert");
    expect(errorContainer).toHaveAttribute("aria-live", "assertive");
  });
});
