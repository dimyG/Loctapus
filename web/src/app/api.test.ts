import { describe, expect, it } from "vitest";
import { getErrorMessage } from "./api";

describe("getErrorMessage", () => {
  it("surfaces a FastAPI string detail", () => {
    const error = { status: 409, data: { detail: "email already registered" } };
    expect(getErrorMessage(error)).toBe("email already registered");
  });

  it("maps 422 array details to friendly validation copy", () => {
    const error = {
      status: 422,
      data: { detail: [{ loc: ["body", "password"], msg: "string too short" }] },
    };
    expect(getErrorMessage(error)).toBe("Check the highlighted fields and try again.");
  });

  it("maps fetch failures to retryable network copy", () => {
    const error = { status: "FETCH_ERROR", data: undefined, error: "TypeError: Failed to fetch" };
    expect(getErrorMessage(error)).toBe(
      "Could not reach the server. Check your connection and try again.",
    );
  });

  it("falls back to a generic message for unknown shapes", () => {
    expect(getErrorMessage("nope")).toBe("Something went wrong. Please try again.");
  });
});
