import { outlinedInputClasses } from "@mui/material/OutlinedInput";
import { createTheme } from "@mui/material/styles";
import type { Theme } from "@mui/material/styles";
import { describe, expect, it } from "vitest";
import { gray } from "../themePrimitives";
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

  it("gives disabled primary buttons a readable muted skin in both schemes", () => {
    const root = inputsCustomizations.MuiButton?.styleOverrides?.root;
    expect(typeof root).toBe("function");
    const callback = root as (props: { theme: Theme }) => Record<string, unknown>;
    const result = callback({
      theme: createTheme({
        // Mirrors AppTheme's css-variables setup so applyStyles emits the
        // data-attribute dark selector the runtime theme uses.
        cssVariables: { colorSchemeSelector: "data-mui-color-scheme" },
        colorSchemes: { light: {}, dark: {} },
      }),
    });
    const variants = result.variants as Array<{
      props: { color?: string; variant?: string };
      style: Record<string, Record<string, unknown>>;
    }>;
    const primaryContained = variants.find(
      (v) => v.props.color === "primary" && v.props.variant === "contained",
    );
    expect(primaryContained).toBeDefined();
    if (primaryContained === undefined) {
      return;
    }
    // The default disabled skin is a washed-out overlay that can match the
    // surrounding surface, so both schemes pin their own flat muted pair.
    expect(primaryContained.style["&.Mui-disabled"]).toMatchObject({
      color: gray[600],
      backgroundColor: gray[200],
      backgroundImage: "none",
      boxShadow: "none",
    });
    const darkKey = Object.keys(primaryContained.style).find((key) => key.includes("dark"));
    expect(darkKey).toBeDefined();
    if (darkKey === undefined) {
      return;
    }
    const dark = primaryContained.style[darkKey];
    expect(dark["&.Mui-disabled"]).toMatchObject({
      color: gray[300],
      backgroundColor: gray[700],
      backgroundImage: "none",
      boxShadow: "none",
    });
  });
});
