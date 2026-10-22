import { outlinedInputClasses } from "@mui/material/OutlinedInput";
import { createTheme } from "@mui/material/styles";
import type { Theme } from "@mui/material/styles";
import { describe, expect, it } from "vitest";
import { inputsCustomizations } from "./inputs";

/** Resolves a style override to a plain object, invoking callbacks with a default theme. */
function resolveOverride(override: unknown): Record<string, unknown> {
  if (typeof override === "function") {
    const callback = override as (props: { theme: Theme }) => Record<string, unknown>;
    return callback({ theme: createTheme() });
  }
  return (override ?? {}) as Record<string, unknown>;
}

const outlinedInput = inputsCustomizations.MuiOutlinedInput?.styleOverrides;

describe("inputsCustomizations", () => {
  it("gives the floating label a notch gap", () => {
    const notchedOutline = resolveOverride(outlinedInput?.notchedOutline);
    expect(typeof notchedOutline.border).toBe("string");
    expect(notchedOutline.border).not.toBe("");
  });

  it("lets the form label float free", () => {
    const root = resolveOverride(inputsCustomizations.MuiFormLabel?.styleOverrides?.root);
    expect(root).not.toHaveProperty("marginBottom");
  });

  it("keeps the input root borderless and focus-ring-free", () => {
    const root = resolveOverride(outlinedInput?.root);
    expect(root).not.toHaveProperty("border");
    const focused = resolveOverride(root[`&.${outlinedInputClasses.focused}`]);
    expect(focused).not.toHaveProperty("outline");
  });
});
