import { ThemeProvider, createTheme } from "@mui/material/styles";
import type { ThemeOptions } from "@mui/material/styles";
import { useMemo } from "react";
import type { ReactNode } from "react";
import { dataDisplayCustomizations } from "./customizations/dataDisplay";
import { feedbackCustomizations } from "./customizations/feedback";
import { inputsCustomizations } from "./customizations/inputs";
import { navigationCustomizations } from "./customizations/navigation";
import { surfacesCustomizations } from "./customizations/surfaces";
import { colorSchemes, shape, shadows, typography } from "./themePrimitives";

interface AppThemeProps {
  children: ReactNode;
  themeComponents?: ThemeOptions["components"];
}

/**
 * Wraps the app in the ported shared theme: CSS-variable color schemes plus
 * the template's component customizations, extendable via themeComponents.
 *
 * @param {ReactNode} children - Content rendered under the theme provider.
 * @param {ThemeOptions["components"]} themeComponents - Extra component overrides merged after the built-in ones.
 */
export default function AppTheme(props: AppThemeProps) {
  const { children, themeComponents } = props;
  const theme = useMemo(() => {
    return createTheme({
      // For details about CSS variables configuration, see
      // https://mui.com/material-ui/customization/css-theme-variables/configuration/.
      // The "template" prefix matches the var(--template-palette-baseShadow)
      // the shadow scale in themePrimitives.ts swaps in.
      cssVariables: {
        colorSchemeSelector: "data-mui-color-scheme",
        cssVarPrefix: "template",
      },
      colorSchemes,
      typography,
      shadows,
      shape,
      components: {
        ...inputsCustomizations,
        ...dataDisplayCustomizations,
        ...feedbackCustomizations,
        ...navigationCustomizations,
        ...surfacesCustomizations,
        ...themeComponents,
      },
    });
  }, [themeComponents]);
  return (
    // The color scheme flips instantly; transitions would otherwise animate the whole palette.
    <ThemeProvider theme={theme} disableTransitionOnChange>
      {children}
    </ThemeProvider>
  );
}
