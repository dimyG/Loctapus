import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import MarketingLayout from "../../layouts/MarketingLayout";

/** The public about page; stays reachable for signed-in visitors. */
export default function AboutPage() {
  return (
    <MarketingLayout>
      <Stack spacing={3} sx={{ py: { xs: 6, md: 10 } }}>
        <Typography component="h1" variant="h3" sx={{ fontWeight: 600 }}>
          About RAG
        </Typography>
        <Typography variant="body1" color="text.secondary">
          RAG is a retrieval-augmented generation workspace. Group your documents into projects and
          teams, then ask questions grounded in your own material instead of a general-purpose
          model's guesswork.
        </Typography>
        <Typography variant="body1" color="text.secondary">
          Documents, semantic search, and answers are rolling out next. This release covers the
          foundation: accounts, sessions, teams, and projects.
        </Typography>
      </Stack>
    </MarketingLayout>
  );
}
