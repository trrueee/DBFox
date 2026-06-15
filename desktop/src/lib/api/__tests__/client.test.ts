import { afterEach, describe, expect, it, vi } from "vitest";
import { request, ApiError, getUserErrorMessage } from "../client";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("API client request error normalization", () => {
  it("creates ApiError with standard fields", () => {
    const error = new ApiError("Error message", 400, "BAD_REQUEST", ["check1"], { detail: "info" });
    expect(error.message).toBe("Error message");
    expect(error.status).toBe(400);
    expect(error.code).toBe("BAD_REQUEST");
    expect(error.checks).toEqual(["check1"]);
    expect(error.detail).toEqual({ detail: "info" });
  });

  it("getUserErrorMessage resolves the error string correctly", () => {
    const apiError = new ApiError("Api Error Msg");
    const regularError = new Error("Regular Error Msg");
    expect(getUserErrorMessage(apiError)).toBe("Api Error Msg");
    expect(getUserErrorMessage(regularError)).toBe("Regular Error Msg");
    expect(getUserErrorMessage("String error")).toBe("String error");
    expect(getUserErrorMessage(null)).toBe("操作失败，请重试");
  });

  it("handles non-JSON error response from fetch", async () => {
    const mockResponse = {
      ok: false,
      status: 500,
      text: async () => "Internal Server Error Text",
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(mockResponse));

    await expect(request("/test")).rejects.toThrow(ApiError);
    try {
      await request("/test");
    } catch (e: unknown) {
      const err = e as ApiError;
      expect(err).toBeInstanceOf(ApiError);
      expect(err.status).toBe(500);
      expect(err.message).toBe("Internal Server Error Text");
    }
  });

  it("handles FastAPI structured validation detail errors", async () => {
    const fastapiPayload = {
      detail: [
        {
          loc: ["body", "db_type"],
          msg: "Field required",
          type: "value_error.missing",
        },
      ],
    };
    const mockResponse = {
      ok: false,
      status: 422,
      text: async () => JSON.stringify(fastapiPayload),
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(mockResponse));

    try {
      await request("/test");
    } catch (e: unknown) {
      const err = e as ApiError;
      expect(err).toBeInstanceOf(ApiError);
      expect(err.status).toBe(422);
      expect(err.message).toBe("Field required");
      expect(err.code).toBe("VALIDATION_ERROR");
    }
  });

  it("handles detail object with code and message", async () => {
    const customPayload = {
      detail: {
        code: "INVALID_CREDENTIALS",
        message: "Your password was incorrect.",
        checks: ["passphrase_format"],
      },
    };
    const mockResponse = {
      ok: false,
      status: 401,
      text: async () => JSON.stringify(customPayload),
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(mockResponse));

    try {
      await request("/test");
    } catch (e: unknown) {
      const err = e as ApiError & { checks?: string[] };
      expect(err).toBeInstanceOf(ApiError);
      expect(err.status).toBe(401);
      expect(err.message).toBe("Your password was incorrect.");
      expect(err.code).toBe("INVALID_CREDENTIALS");
      expect(err.checks).toEqual(["passphrase_format"]);
    }
  });
});
