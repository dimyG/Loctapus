import Box from "@mui/material/Box";
import Container from "@mui/material/Container";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import type { ReactNode } from "react";
import SiteFooter from "./SiteFooter";

/** Public-facing frame: wordmark header and content above the shared site footer. */
export default function MarketingLayout({ children }: { children: ReactNode }) {
  return (
    <Box sx={{ minHeight: "100dvh", display: "flex", flexDirection: "column" }}>
      <Container maxWidth="md" sx={{ py: 4, flexGrow: 1 }}>
        <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "center" }}>
          <Typography variant="h6" sx={{ fontWeight: 600 }}>
            RAG
          </Typography>
        </Stack>
        {children}
      </Container>
      <SiteFooter maxWidth="md" />
    </Box>
  );
}
