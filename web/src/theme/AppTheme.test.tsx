import { useTheme } from "@mui/material/styles";
import type { CssVarsTheme, Theme } from "@mui/material/styles";
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import AppTheme from "./AppTheme";
import { brand, gray } from "./themePrimitives";

/** Reads the theme AppTheme provides and hands it to the capturing test. */
function ThemeProbe({ onCapture }: { onCapture: (theme: Theme) => void }) {
  onCapture(useTheme());
  return null;
}

/** Renders one probe inside AppTheme and returns the theme the probe received. */
function renderProbedTheme(): Theme {
  let captured!: Theme;
  render(
    <AppTheme>
      <ThemeProbe onCapture={(theme) => (captured = theme)} />
    </AppTheme>,
  );
  return captured;
}

describe("AppTheme", () => {
  it("renders children under the template theme", () => {
    expect(renderProbedTheme().palette.mode).toBe("light");
  });

  it("applies the template typography and palette", () => {
    const theme = renderProbedTheme();
    expect(theme.typography.fontFamily).toContain("Inter");
    expect(theme.palette.primary.main).toBe(brand[400]);
  });

  it("resolves the dark scheme", () => {
    // The base Theme type omits colorSchemes unless CssThemeVariables is
    // augmented, so the captured theme is viewed through the vars-aware type.
    const theme = renderProbedTheme() as unknown as CssVarsTheme;
    expect(theme.colorSchemes.dark).toBeDefined();
    expect(theme.colorSchemes.dark?.palette.background.default).toBe(gray[900]);
  });

  it("applies the ported component customizations", () => {
    expect(renderProbedTheme().components?.MuiMenuItem?.styleOverrides).toBeDefined();
  });
});
