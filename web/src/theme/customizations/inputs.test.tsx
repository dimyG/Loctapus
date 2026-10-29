import { outlinedInputClasses } from "@mui/material/OutlinedInput";
import { createTheme } from "@mui/material/styles";
import type { Theme } from "@mui/material/styles";
import { describe, expect, it } from "vitest";
import { brand, gray } from "../themePrimitives";
import { inputsCustomizations } from "./inputs";

/** Resolves a style override to a plain object, invoking callbacks with a default theme. */
function resolveOverride(override: unknown): Record<string, unknown> {
  if (typeof override === "function") {
    const callback = override as (props: { theme: Theme }) => Record<string, unknown>;
    return callback({ theme: createTheme() });
  }
  return (override ?? {}) as Record<string, unknown>;
}

/**
 * Resolves one MuiButton variant block against a dual-scheme theme, returning
 * the light styles and the nested dark-scheme styles.
 */
function resolveButtonVariant(color: string, variant: string) {
  const root = inputsCustomizations.MuiButton?.styleOverrides?.root;
  if (typeof root !== "function") {
    throw new Error("MuiButton root override is not a callback");
  }
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
    style: Record<string, unknown>;
  }>;
  const match = variants.find((v) => v.props.color === color && v.props.variant === variant);
  if (match === undefined) {
    throw new Error(`No MuiButton variant for color=${color} variant=${variant}`);
  }
  const darkKey = Object.keys(match.style).find((key) => key.includes("dark"));
  if (darkKey === undefined) {
    throw new Error(`Variant color=${color} variant=${variant} has no dark-scheme block`);
  }
  return {
    light: match.style,
    dark: match.style[darkKey] as Record<string, unknown>,
  };
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
    const { light, dark } = resolveButtonVariant("primary", "contained");
    // The default disabled skin is a washed-out overlay that can match the
    // surrounding surface, so both schemes pin their own flat muted pair.
    expect(light["&.Mui-disabled"]).toMatchObject({
      color: gray[600],
      backgroundColor: gray[200],
      backgroundImage: "none",
      boxShadow: "none",
    });
    expect(dark["&.Mui-disabled"]).toMatchObject({
      color: gray[300],
      backgroundColor: gray[700],
      backgroundImage: "none",
      boxShadow: "none",
    });
  });

  it("skins dark-scheme primary contained buttons in the Loctapus brand blue", () => {
    const { dark } = resolveButtonVariant("primary", "contained");
    expect(dark.color).toBe("white");
    // The skin is flat: no gradient, no inset shadows, one uniform border.
    // The flat brand[500] fill keeps the white label at WCAG AA contrast
    // (5.2:1) where the logo's brighter brand[400]/[600] fall short.
    expect(dark.backgroundColor).toBe(brand[500]);
    expect(dark.backgroundImage).toBe("none");
    expect(dark.boxShadow).toBe("none");
    expect(dark.border).toBe(`1px solid ${brand[600]}`);
    expect(dark["&:hover"]).toMatchObject({ backgroundColor: brand[700], boxShadow: "none" });
    expect(dark["&:active"]).toMatchObject({ backgroundColor: brand[800] });
  });
});
