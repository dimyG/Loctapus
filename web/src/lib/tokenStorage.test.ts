import { beforeEach, describe, expect, it } from "vitest";
import { clearToken, loadToken, saveToken } from "./tokenStorage";

describe("tokenStorage", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("round-trips a saved token", () => {
    saveToken("t-round");
    expect(loadToken()).toBe("t-round");
  });

  it("returns null when nothing is stored", () => {
    expect(loadToken()).toBeNull();
  });

  it("clears a stored token", () => {
    saveToken("t-clear");
    clearToken();
    expect(loadToken()).toBeNull();
  });
});
