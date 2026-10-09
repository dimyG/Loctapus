import type { ThemeOptions } from "@mui/material/styles";

const headingFont = '"Work Sans", "Helvetica", "Arial", sans-serif';
const bodyFont = '"Inter", "Helvetica", "Arial", sans-serif';

/**
 * Precise shape returned by {@link createAppTheme}; structurally assignable to
 * MUI's ThemeOptions, but with concrete fields instead of its wide unions.
 */
export interface AppTheme {
  palette: { primary: { main: string } };
  shape: { borderRadius: number };
  typography: {
    fontFamily: string;
    h1: { fontFamily: string };
    h2: { fontFamily: string };
    h3: { fontFamily: string };
    h4: { fontFamily: string };
    h5: { fontFamily: string };
    h6: { fontFamily: string };
  };
}

/**
 * Devias-style theme options: one muted accent color, Work Sans headings over
 * Inter body text, and 12px rounded surfaces with subtle 1px borders.
 */
export function createAppTheme(): AppTheme {
  return {
    palette: {
      primary: { main: "#5664D2" },
    },
    shape: { borderRadius: 12 },
    typography: {
      fontFamily: bodyFont,
      h1: { fontFamily: headingFont },
      h2: { fontFamily: headingFont },
      h3: { fontFamily: headingFont },
      h4: { fontFamily: headingFont },
      h5: { fontFamily: headingFont },
      h6: { fontFamily: headingFont },
    },
  } satisfies ThemeOptions;
}
