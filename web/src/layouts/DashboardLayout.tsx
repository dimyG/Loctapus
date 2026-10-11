import AppBar from "@mui/material/AppBar";
import Box from "@mui/material/Box";
import Container from "@mui/material/Container";
import Link from "@mui/material/Link";
import Toolbar from "@mui/material/Toolbar";
import Typography from "@mui/material/Typography";
import type { ReactNode } from "react";
import { Link as RouterLink } from "react-router";
import UserMenu from "../features/auth/UserMenu";
import SiteFooter from "./SiteFooter";

/** Frame for the signed-in pages: topbar with wordmark and account menu, above the site footer. */
export default function DashboardLayout({ children }: { children: ReactNode }) {
  return (
    <Box sx={{ minHeight: "100dvh", display: "flex", flexDirection: "column" }}>
      <AppBar position="static" color="default" elevation={0}>
        <Toolbar sx={{ gap: 2 }}>
          <Link
            component={RouterLink}
            to="/"
            underline="none"
            color="text.primary"
            sx={{ fontWeight: 600 }}
          >
            <Typography variant="h6">RAG</Typography>
          </Link>
          <Box sx={{ flexGrow: 1 }} />
          <UserMenu />
        </Toolbar>
      </AppBar>
      <Container maxWidth="lg" sx={{ py: 4, flexGrow: 1 }}>
        {children}
      </Container>
      <SiteFooter />
    </Box>
  );
}
