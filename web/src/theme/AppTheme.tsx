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
 */
export default function AppTheme(props: AppThemeProps) {
  const { children, themeComponents } = props;
  const theme = useMemo(() => {
    return createTheme({
      // For details about CSS variables configuration, see
      // https://mui.com/material-ui/customization/css-theme-variables/configuration/.
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
    <ThemeProvider theme={theme} disableTransitionOnChange>
      {children}
    </ThemeProvider>
  );
}
