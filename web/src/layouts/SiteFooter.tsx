import Box from "@mui/material/Box";
import Container from "@mui/material/Container";
import Link from "@mui/material/Link";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import type { Breakpoint } from "@mui/material/styles";
import { Link as RouterLink } from "react-router";

/** The shared site footer: copyright and an About link under a hairline rule. */
export default function SiteFooter({ maxWidth = "lg" }: { maxWidth?: Breakpoint }) {
  return (
    <Box component="footer" sx={{ borderTop: 1, borderColor: "divider", py: 3 }}>
      <Container maxWidth={maxWidth}>
        <Stack direction="row" sx={{ justifyContent: "space-between", flexWrap: "wrap", gap: 1 }}>
          <Typography variant="body2" color="text.secondary">
            © {new Date().getFullYear()} RAG. All rights reserved.
          </Typography>
          <Link component={RouterLink} to="/about" variant="body2" color="text.secondary">
            About
          </Link>
        </Stack>
      </Container>
    </Box>
  );
}
