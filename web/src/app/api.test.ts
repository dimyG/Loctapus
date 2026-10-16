import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { projectsApi } from "../features/projects/projectsApi";
import { server } from "../test/server";
import { initialRootState, makeStore } from "./store";
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

describe("session expiry", () => {
  it("clears the session when an authenticated request comes back 401", async () => {
    server.use(
      http.get("*/api/projects", () =>
        HttpResponse.json({ detail: "invalid or expired token" }, { status: 401 }),
      ),
    );
    const testStore = makeStore({
      ...initialRootState(),
      auth: { token: "t-gone", user: { id: "u-1", email: "user@example.test" }, status: "idle" },
    });
    const action = testStore.dispatch(projectsApi.endpoints.getProjects.initiate());
    await action.then(
      () => undefined,
      () => undefined,
    );
    expect(testStore.getState().auth.token).toBeNull();
    expect(testStore.getState().auth.user).toBeNull();
  });
});
