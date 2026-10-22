import { createTheme } from "@mui/material/styles";
import type { Theme } from "@mui/material/styles";
import { describe, expect, it } from "vitest";
import { surfacesCustomizations } from "./surfaces";

/** Resolves the dialog paper override against a css-variable theme so dark styles stay inspectable. */
function resolveDialogPaper(): Record<string, unknown> {
  const theme = createTheme({
    cssVariables: true,
    colorSchemes: { light: {}, dark: {} },
  });
  const override = surfacesCustomizations.MuiDialog?.styleOverrides?.paper;
  if (typeof override === "function") {
    const callback = override as (props: { theme: Theme }) => Record<string, unknown>;
    return callback({ theme });
  }
  return (override ?? {}) as Record<string, unknown>;
}

describe("surfacesCustomizations", () => {
  it("tints the dark dialog paper toward the brand slate without touching light mode", () => {
    const paper = resolveDialogPaper();

    // The dark selector key (e.g. a prefers-color-scheme media query) carries the brand tint.
    const darkKey = Object.keys(paper).find((key) => key.includes("dark"));
    expect(darkKey).toBeDefined();
    const darkStyles = paper[darkKey as string] as Record<string, unknown>;
    expect(darkStyles.backgroundImage).toBe("none");
    expect(darkStyles.backgroundColor).toBe("hsl(210, 30%, 14%)");

    // Top-level styles would also apply in light mode, so they must stay empty.
    expect(paper).not.toHaveProperty("backgroundImage");
    expect(paper).not.toHaveProperty("backgroundColor");
  });
});
