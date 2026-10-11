import Box from "@mui/material/Box";
import Card from "@mui/material/Card";
import Container from "@mui/material/Container";
import Link from "@mui/material/Link";
import Typography from "@mui/material/Typography";
import type { ReactNode } from "react";
import { Link as RouterLink } from "react-router";
import SiteFooter from "./SiteFooter";

/** Frame for the auth pages: a centered card under the wordmark, above the site footer. */
export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <Box sx={{ minHeight: "100dvh", display: "flex", flexDirection: "column" }}>
      <Container maxWidth="xs" sx={{ py: { xs: 6, md: 10 }, flexGrow: 1 }}>
        <Box sx={{ mb: 3, textAlign: "center" }}>
          <Link
            component={RouterLink}
            to="/"
            underline="none"
            color="text.primary"
            sx={{ fontWeight: 600 }}
          >
            <Typography variant="h6">RAG</Typography>
          </Link>
        </Box>
        <Card variant="outlined" sx={{ p: 4 }}>
          {children}
        </Card>
      </Container>
      <SiteFooter maxWidth="xs" />
    </Box>
  );
}
