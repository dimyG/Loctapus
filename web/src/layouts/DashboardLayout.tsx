import AppBar from "@mui/material/AppBar";
import Container from "@mui/material/Container";
import Link from "@mui/material/Link";
import Toolbar from "@mui/material/Toolbar";
import Typography from "@mui/material/Typography";
import type { ReactNode } from "react";
import { Link as RouterLink } from "react-router";
import UserMenu from "../features/auth/UserMenu";

/** Frame for the signed-in pages: topbar with wordmark and account menu. */
export default function DashboardLayout({ children }: { children: ReactNode }) {
  return (
    <>
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
          <UserMenu />
        </Toolbar>
      </AppBar>
      <Container maxWidth="lg" sx={{ py: 4 }}>
        {children}
      </Container>
    </>
  );
}
