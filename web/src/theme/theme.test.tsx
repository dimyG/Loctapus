import { describe, expect, it } from "vitest";
import { createAppTheme } from "./theme";

describe("createAppTheme", () => {
  it("matches the Devias palette and type stack", () => {
    const theme = createAppTheme();
    expect(theme.palette?.primary?.main).toBe("#5664D2");
    expect(theme.typography?.h1?.fontFamily).toContain('"Work Sans"');
    expect(theme.typography?.fontFamily).toContain('"Inter"');
    expect(theme.shape?.borderRadius).toBe(12);
  });
});
