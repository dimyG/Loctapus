import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { initialRootState, makeStore } from "../../app/store";
import { loadToken, saveToken } from "../../lib/tokenStorage";
import { server } from "../../test/server";
import { bootstrapAuth, loginUser, logoutUser, registerUser } from "./authSlice";

const authenticated = {
  auth: {
    token: "t-login",
    user: { id: "u-1", email: "user@example.test" },
    status: "idle" as const,
  },
};

describe("auth session", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("login stores the token and hydrates the user", async () => {
    const testStore = makeStore();
    const user = await testStore
      .dispatch(loginUser({ email: "user@example.test", password: "password123" }))
      .unwrap();
    expect(user).toEqual({ id: "u-1", email: "user@example.test" });
    const state = testStore.getState();
    expect(state.auth.token).toBe("t-login");
    expect(loadToken()).toBe("t-login");
    expect(state.auth.user).toEqual({ id: "u-1", email: "user@example.test" });
  });

  it("register then 409 rejects without storing", async () => {
    server.use(
      http.post("*/auth/register", () =>
        HttpResponse.json({ detail: "email already registered" }, { status: 409 }),
      ),
    );
    const testStore = makeStore();
    await expect(
      testStore
        .dispatch(registerUser({ email: "user@example.test", password: "password123" }))
        .unwrap(),
    ).rejects.toMatchObject({ status: 409 });
    const state = testStore.getState();
    expect(state.auth.token).toBeNull();
    expect(state.auth.user).toBeNull();
    expect(loadToken()).toBeNull();
  });

  it("logout posts, clears storage and resets the api cache even when the call fails", async () => {
    const logoutCalls: unknown[] = [];
    server.use(
      http.post("*/auth/logout", ({ request }) => {
        logoutCalls.push(request);
        return HttpResponse.json({ detail: "boom" }, { status: 500 });
      }),
    );
    saveToken("t-login");
    const testStore = makeStore({
      ...initialRootState(),
      ...authenticated,
      api: { ...initialRootState().api, queries: { seeded: undefined as never } },
    });
    await testStore.dispatch(logoutUser());
    expect(logoutCalls).toHaveLength(1);
    expect(loadToken()).toBeNull();
    const state = testStore.getState();
    expect(state.auth.token).toBeNull();
    expect(state.auth.user).toBeNull();
    expect(state.api.queries).toEqual({});
  });

  it("logout clears the local session before the revocation completes", async () => {
    let resolveRequest: (() => void) | undefined;
    server.use(
      http.post("*/auth/logout", async () => {
        await new Promise<void>((resolve) => {
          resolveRequest = resolve;
        });
        return new HttpResponse(null, { status: 204 });
      }),
    );
    saveToken("t-login");
    const testStore = makeStore({
      ...initialRootState(),
      ...authenticated,
      api: { ...initialRootState().api, queries: { seeded: undefined as never } },
    });
    const action = testStore.dispatch(logoutUser());
    // The session must already be gone while the revocation hangs.
    expect(loadToken()).toBeNull();
    const state = testStore.getState();
    expect(state.auth.token).toBeNull();
    expect(state.auth.user).toBeNull();
    expect(state.api.queries).toEqual({});
    await vi.waitFor(() => {
      expect(resolveRequest).toBeDefined();
    });
    resolveRequest?.();
    await action;
  });

  it("keeps the stored token when bootstrap fails for a non-401 reason", async () => {
    server.use(http.get("*/users/me", () => HttpResponse.error()));
    saveToken("t-keep");
    const testStore = makeStore();
    await expect(testStore.dispatch(bootstrapAuth()).unwrap()).rejects.toBeDefined();
    const state = testStore.getState();
    expect(state.auth.token).toBe("t-keep");
    expect(loadToken()).toBe("t-keep");
    expect(state.auth.status).toBe("idle");
  });

  it("bootstrap with no stored token fulfills null", async () => {
    const testStore = makeStore();
    const result = await testStore.dispatch(bootstrapAuth()).unwrap();
    expect(result).toBeNull();
    const state = testStore.getState();
    expect(state.auth.user).toBeNull();
    expect(state.auth.status).toBe("idle");
  });

  it("bootstrap with a valid stored token hydrates the user", async () => {
    saveToken("t-login");
    const testStore = makeStore();
    expect(testStore.getState().auth.status).toBe("booting");
    const user = await testStore.dispatch(bootstrapAuth()).unwrap();
    expect(user).toEqual({ id: "u-1", email: "user@example.test" });
    expect(testStore.getState().auth.user).toEqual({ id: "u-1", email: "user@example.test" });
  });

  it("bootstrap with a revoked stored token clears everything", async () => {
    server.use(
      http.get("*/users/me", () =>
        HttpResponse.json({ detail: "Not authenticated" }, { status: 401 }),
      ),
    );
    saveToken("t-revoked");
    const testStore = makeStore();
    await expect(testStore.dispatch(bootstrapAuth()).unwrap()).rejects.toMatchObject({
      status: 401,
    });
    const state = testStore.getState();
    expect(state.auth.token).toBeNull();
    expect(state.auth.user).toBeNull();
    expect(loadToken()).toBeNull();
  });

  it("status tracks busy while a login is in flight", async () => {
    let resolveRequest: (() => void) | undefined;
    let requestSeen = false;
    server.use(
      http.post("*/auth/login", async () => {
        requestSeen = true;
        await new Promise<void>((resolve) => {
          resolveRequest = resolve;
        });
        return HttpResponse.json({ access_token: "t-login", token_type: "bearer" });
      }),
    );
    const testStore = makeStore();
    const action = testStore.dispatch(
      loginUser({ email: "user@example.test", password: "password123" }),
    );
    expect(testStore.getState().auth.status).toBe("busy");
    await vi.waitFor(() => {
      expect(requestSeen).toBe(true);
    });
    resolveRequest?.();
    await action.unwrap();
    expect(testStore.getState().auth.status).toBe("idle");
  });
});
