import Card from "@mui/material/Card";
import Container from "@mui/material/Container";
import Link from "@mui/material/Link";
import Stack from "@mui/material/Stack";
import { styled } from "@mui/material/styles";
import type { ReactNode } from "react";
import { Link as RouterLink } from "react-router";
import ColorModeIconDropdown from "../theme/ColorModeIconDropdown";
import BrandMark from "./BrandMark";

/** Full-height centered column with the sign-in template's soft radial backdrop. */
const FrameStack = styled(Stack)(({ theme }) => ({
  minHeight: "100dvh",
  justifyContent: "center",
  position: "relative",
  "&::before": {
    content: '""',
    display: "block",
    position: "absolute",
    zIndex: -1,
    inset: 0,
    backgroundImage: "radial-gradient(ellipse at 50% 50%, hsl(210, 100%, 97%), hsl(0, 0%, 100%))",
    backgroundRepeat: "no-repeat",
    ...theme.applyStyles("dark", {
      backgroundImage: "radial-gradient(at 50% 50%, hsla(210, 100%, 16%, 0.5), hsl(220, 30%, 5%))",
    }),
  },
}));

/**
 * The auth frame: the sign-in template's shell around the page's form. The
 * mode switcher is pinned top-right; the wordmark and the outlined card are
 * centered in an xs column.
 */
export default function AuthFrame({ children }: { children: ReactNode }) {
  return (
    <FrameStack direction="column">
      <ColorModeIconDropdown sx={{ position: "fixed", top: "1rem", right: "1rem" }} />
      <Container maxWidth="xs" sx={{ py: 4, display: "flex", flexDirection: "column", gap: 2 }}>
        <Link
          component={RouterLink}
          to="/"
          underline="none"
          color="text.primary"
          sx={{ fontWeight: 600, textAlign: "center" }}
        >
          <BrandMark />
        </Link>
        <Card variant="outlined" sx={{ p: 4 }}>
          {children}
        </Card>
      </Container>
    </FrameStack>
  );
}
