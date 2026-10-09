import CircularProgress from "@mui/material/CircularProgress";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

/** Full-page splash shown while a stored token is being validated. */
export default function BootSplash() {
  return (
    <Stack sx={{ minHeight: "100dvh", justifyContent: "center", alignItems: "center" }} spacing={2}>
      <CircularProgress size={32} />
      <Typography color="text.secondary">Preparing your workspace</Typography>
    </Stack>
  );
}
