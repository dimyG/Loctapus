import Container from "@mui/material/Container";
import Divider from "@mui/material/Divider";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import type { ReactNode } from "react";

/** Public-facing frame: wordmark header, content slot, and a subtle footer. */
export default function MarketingLayout({ children }: { children: ReactNode }) {
  return (
    <Container maxWidth="md" sx={{ py: 4, minHeight: "100dvh" }}>
      <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "center" }}>
        <Typography variant="h6" sx={{ fontWeight: 600 }}>
          RAG
        </Typography>
      </Stack>
      {children}
      <Divider sx={{ my: 5 }} />
      <Typography variant="body2" color="text.secondary">
        RAG - document intelligence for small teams.
      </Typography>
    </Container>
  );
}
