import Container from "@mui/material/Container";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import MarketingFrame from "../../layouts/MarketingFrame";

/** The public about page; stays reachable for signed-in visitors. */
export default function AboutPage() {
  return (
    <MarketingFrame>
      <Container maxWidth="md" sx={{ pt: { xs: 14, sm: 20 }, pb: { xs: 8, sm: 12 } }}>
        <Stack spacing={3}>
          <Typography component="h1" variant="h3" sx={{ fontWeight: 600 }}>
            About RAG
          </Typography>
          {/* Draft copy pending the owner's review; do not treat as final product text. */}
          <Typography variant="body1" color="text.secondary">
            RAG is a retrieval-augmented generation workspace. Group your documents into projects
            and teams, then ask questions grounded in your own material instead of a general-purpose
            model's guesswork.
          </Typography>
          <Typography variant="body1" color="text.secondary">
            Documents, semantic search, and answers are rolling out next. This release covers the
            foundation: accounts, sessions, teams, and projects.
          </Typography>
        </Stack>
      </Container>
    </MarketingFrame>
  );
}
