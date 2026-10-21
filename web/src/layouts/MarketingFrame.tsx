import AppBar from "@mui/material/AppBar";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Container from "@mui/material/Container";
import Link from "@mui/material/Link";
import Stack from "@mui/material/Stack";
import Toolbar from "@mui/material/Toolbar";
import Typography from "@mui/material/Typography";
import { alpha, styled } from "@mui/material/styles";
import type { ReactNode } from "react";
import { Link as RouterLink } from "react-router";
import ColorModeIconDropdown from "../theme/ColorModeIconDropdown";

/** The floating pill toolbar, ported from the marketing template's AppAppBar. */
const StyledToolbar = styled(Toolbar)(({ theme }) => ({
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  flexShrink: 0,
  borderRadius: `calc(${theme.shape.borderRadius}px + 8px)`,
  backdropFilter: "blur(24px)",
  border: "1px solid",
  borderColor: (theme.vars || theme).palette.divider,
  backgroundColor: theme.vars
    ? `rgba(${theme.vars.palette.background.defaultChannel} / 0.4)`
    : alpha(theme.palette.background.default, 0.4),
  boxShadow: (theme.vars || theme).shadows[1],
  padding: "8px 12px",
}));

/**
 * The marketing frame: the template's floating navbar above the children, the
 * copyright footer below. Pages bring their own sections and containers.
 */
export default function MarketingFrame({ children }: { children: ReactNode }) {
  return (
    <Box>
      <AppBar
        position="fixed"
        enableColorOnDark
        sx={{
          boxShadow: 0,
          bgcolor: "transparent",
          backgroundImage: "none",
          mt: "calc(var(--template-frame-height, 0px) + 28px)",
        }}
      >
        <Container maxWidth="lg">
          <StyledToolbar variant="dense" disableGutters>
            <Box sx={{ flexGrow: 1, display: "flex", alignItems: "center", gap: 1 }}>
              <Link
                component={RouterLink}
                to="/"
                underline="none"
                color="text.primary"
                sx={{ fontWeight: 600 }}
              >
                <Typography variant="h6">RAG</Typography>
              </Link>
              <Button variant="text" color="info" size="small" component={RouterLink} to="/about">
                About
              </Button>
            </Box>
            <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
              <Button
                color="primary"
                variant="text"
                size="small"
                component={RouterLink}
                to="/login"
              >
                Sign in
              </Button>
              <Button
                color="primary"
                variant="contained"
                size="small"
                component={RouterLink}
                to="/register"
              >
                Get started
              </Button>
              <ColorModeIconDropdown />
            </Stack>
          </StyledToolbar>
        </Container>
      </AppBar>
      {children}
      <Box component="footer" sx={{ borderTop: "1px solid", borderColor: "divider" }}>
        <Container maxWidth="lg" sx={{ py: 4 }}>
          <Typography variant="body2" color="text.secondary">
            © {new Date().getFullYear()} RAG. All rights reserved.
          </Typography>
        </Container>
      </Box>
    </Box>
  );
}
