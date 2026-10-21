import ChatBubbleRoundedIcon from "@mui/icons-material/ChatBubbleRounded";
import PostAddRoundedIcon from "@mui/icons-material/PostAddRounded";
import UploadFileRoundedIcon from "@mui/icons-material/UploadFileRounded";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import Container from "@mui/material/Container";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { Link as RouterLink, Navigate } from "react-router";
import { useAppSelector } from "../../app/hooks";
import MarketingFrame from "../../layouts/MarketingFrame";
import { selectAuthStatus, selectUser } from "../auth/authSlice";

const steps = [
  {
    icon: <PostAddRoundedIcon />,
    title: "Create a project",
    description: "Group your documents in one place and share them with a team.",
  },
  {
    icon: <UploadFileRoundedIcon />,
    title: "Upload documents",
    description: "Add PDFs and text files; every file is stored and tracked.",
  },
  {
    icon: <ChatBubbleRoundedIcon />,
    title: "Ask questions",
    description: "Ask in plain language and get answers that cite the source.",
  },
];

/** The public landing page; signed-in visitors are redirected to their projects. */
export default function LandingPage() {
  // The hydrated user, not the stored token, drives the redirect: a visitor
  // whose token has gone stale must stay on the public landing instead of
  // being bounced to /login by the guarded route. Only settled sessions
  // redirect: during sign-out the stale user rides along with a "busy"
  // status, and redirecting then would land the user on /app, which
  // bounces to /login once the session clears (spec 6.2).
  const user = useAppSelector(selectUser);
  const status = useAppSelector(selectAuthStatus);
  if (user !== null && status === "idle") {
    return <Navigate to="/app" replace />;
  }

  return (
    <MarketingFrame>
      <Box
        id="hero"
        sx={(theme) => ({
          width: "100%",
          backgroundRepeat: "no-repeat",
          backgroundImage:
            "radial-gradient(ellipse 80% 50% at 50% -20%, hsl(210, 100%, 90%), transparent)",
          ...theme.applyStyles("dark", {
            backgroundImage:
              "radial-gradient(ellipse 80% 50% at 50% -20%, hsl(210, 100%, 16%), transparent)",
          }),
        })}
      >
        <Container
          sx={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            pt: { xs: 14, sm: 20 },
            pb: { xs: 8, sm: 12 },
          }}
        >
          <Stack
            spacing={2}
            useFlexGap
            sx={{ alignItems: "center", width: { xs: "100%", sm: "70%" } }}
          >
            <Typography
              component="h1"
              sx={{
                fontSize: "clamp(2.5rem, 8vw, 3.5rem)",
                fontWeight: 600,
                textAlign: "center",
              }}
            >
              Your documents, searchable by meaning - upload, ask, get grounded answers
            </Typography>
            <Typography
              variant="h6"
              color="text.secondary"
              sx={{ fontWeight: 400, textAlign: "center", width: { sm: "100%", md: "80%" } }}
            >
              A private workspace where your team stores its documents and asks questions in
              everyday language.
            </Typography>
            <Stack
              direction={{ xs: "column", sm: "row" }}
              spacing={1}
              useFlexGap
              sx={{ pt: 2, width: { xs: "100%", sm: "350px" } }}
            >
              <Button variant="contained" component={RouterLink} to="/register">
                Get started
              </Button>
              <Button variant="outlined" component={RouterLink} to="/login">
                Sign in
              </Button>
            </Stack>
          </Stack>
        </Container>
      </Box>
      <Container maxWidth="lg" sx={{ pb: { xs: 8, sm: 16 } }}>
        <Stack direction={{ xs: "column", md: "row" }} spacing={3}>
          {steps.map((step) => (
            <Card key={step.title} variant="outlined" sx={{ flex: 1, p: 3 }}>
              <Box sx={{ color: "primary.main", mb: 1.5 }}>{step.icon}</Box>
              <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
                {step.title}
              </Typography>
              <Box sx={{ mt: 1 }} />
              <Typography variant="body2" color="text.secondary">
                {step.description}
              </Typography>
            </Card>
          ))}
        </Stack>
      </Container>
    </MarketingFrame>
  );
}
