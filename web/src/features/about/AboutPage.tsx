import GitHubIcon from "@mui/icons-material/GitHub";
import Button from "@mui/material/Button";
import Container from "@mui/material/Container";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { repositoryUrl } from "../../app/repository";
import MarketingFrame from "../../layouts/MarketingFrame";

/** The public about page; stays reachable for signed-in visitors. */
export default function AboutPage() {
  return (
    <MarketingFrame>
      <Container maxWidth="md" sx={{ pt: { xs: 14, sm: 20 }, pb: { xs: 8, sm: 12 } }}>
        <Stack spacing={3} sx={{ alignItems: "flex-start" }}>
          <Typography component="h1" variant="h3" sx={{ fontWeight: 600 }}>
            About Loctapus
          </Typography>
          <Typography variant="body1" color="text.secondary">
            Loctapus is a platform that brings together knowledge from multiple sources into a
            unified, searchable knowledge base and makes it accessible to applications, AI agents,
            and users through various interfaces, including web chat, APIs, and MCP.
          </Typography>
          <Typography variant="body1" color="text.secondary">
            The project is still under development. It is open source, so you can follow its
            progress and read the code on GitHub.
          </Typography>
          <Button
            variant="outlined"
            startIcon={<GitHubIcon />}
            href={repositoryUrl}
            target="_blank"
            rel="noopener noreferrer"
          >
            View on GitHub
          </Button>
        </Stack>
      </Container>
    </MarketingFrame>
  );
}
