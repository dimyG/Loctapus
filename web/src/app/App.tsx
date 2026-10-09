import CssBaseline from "@mui/material/CssBaseline";
import Typography from "@mui/material/Typography";
import { ThemeProvider, createTheme } from "@mui/material/styles";
import { createAppTheme } from "../theme/theme";

const theme = createTheme(createAppTheme());

/** Root component: applies the theme and renders the placeholder wordmark shell. */
export default function App() {
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Typography component="h1" variant="h1" align="center" sx={{ mt: 8 }}>
        RAG
      </Typography>
    </ThemeProvider>
  );
}
