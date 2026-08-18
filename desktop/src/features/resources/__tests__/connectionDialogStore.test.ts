import { beforeEach, describe, expect, it } from "vitest";
import { useConnectionDialogStore } from "../connectionDialogStore";

describe("connectionDialogStore", () => {
  beforeEach(() => {
    useConnectionDialogStore.setState({ open: false, createMode: true });
  });

  it("opens in create mode", () => {
    useConnectionDialogStore.getState().openCreate();
    expect(useConnectionDialogStore.getState()).toMatchObject({
      open: true,
      createMode: true,
    });
  });

  it("opens in detail mode", () => {
    useConnectionDialogStore.getState().openDetail();
    expect(useConnectionDialogStore.getState()).toMatchObject({
      open: true,
      createMode: false,
    });
  });

  it("closes the dialog", () => {
    useConnectionDialogStore.getState().openCreate();
    useConnectionDialogStore.getState().close();
    expect(useConnectionDialogStore.getState().open).toBe(false);
  });
});
