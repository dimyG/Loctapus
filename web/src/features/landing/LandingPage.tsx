import ChatBubbleRoundedIcon from "@mui/icons-material/ChatBubbleRounded";
import CloudSyncRoundedIcon from "@mui/icons-material/CloudSyncRounded";
import GroupsRoundedIcon from "@mui/icons-material/GroupsRounded";
import InsightsRoundedIcon from "@mui/icons-material/InsightsRounded";
import RocketLaunchRoundedIcon from "@mui/icons-material/RocketLaunchRounded";
import SmartToyRoundedIcon from "@mui/icons-material/SmartToyRounded";
import SupportAgentRoundedIcon from "@mui/icons-material/SupportAgentRounded";
import SyncRoundedIcon from "@mui/icons-material/SyncRounded";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import Chip from "@mui/material/Chip";
import Container from "@mui/material/Container";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { Link as RouterLink, Navigate } from "react-router";
import { useAppSelector } from "../../app/hooks";
import MarketingFrame from "../../layouts/MarketingFrame";
import { selectAuthStatus, selectUser } from "../auth/authSlice";

const steps = [
  {
    icon: <CloudSyncRoundedIcon />,
    title: "Connect your knowledge base",
    description: "Upload files, connect cloud storages and websites, and keep them in sync.",
    coming: false,
  },
  {
    icon: <ChatBubbleRoundedIcon />,
    title: "Chat in our interface",
    description: "Ask questions inside our web app; it is the simplest way to use the service.",
    coming: false,
  },
  {
    icon: <RocketLaunchRoundedIcon />,
    title: "Deploy an agent",
    description:
      "Give an agent access to your knowledge base where your users need it: your docs page, your app, Slack, your support desk.",
    coming: true,
  },
  {
    icon: <InsightsRoundedIcon />,
    title: "Analyze",
    description: "See what people ask, where your agent shines, and where it struggles.",
    coming: true,
  },
];

const values = [
  {
    icon: <SupportAgentRoundedIcon />,
    title: "Answer complex customer questions",
    description: "Ground every answer in your own documents, with the sources to prove it.",
  },
  {
    icon: <GroupsRoundedIcon />,
    title: "Give your teams a personal assistant",
    description: "An assistant that knows your product, your processes, and your terminology.",
  },
  {
    icon: <SyncRoundedIcon />,
    title: "Keep your knowledge base always up to date",
    description: "Re-asking always reads the latest version of your sources.",
  },
  {
    icon: <SmartToyRoundedIcon />,
    title: "AI agents custom to your enterprise",
    description: "Spin up an agent wherever your users already are, on top of your own knowledge.",
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
              Chat with your company's knowledge base
            </Typography>
            <Typography
              variant="h6"
              color="text.secondary"
              sx={{ fontWeight: 400, textAlign: "center", width: { sm: "100%", md: "80%" } }}
            >
              Deploy AI teammates that understand your data, product, knowledge, and tools. A
              private workspace where your team stores its documents and asks questions in everyday
              language.
            </Typography>
            {/* "Sign in" stays in the navbar only; the hero keeps the single
            centered primary action (spec decision 7). */}
            <Stack direction="row" useFlexGap sx={{ pt: 2, justifyContent: "center" }}>
              <Button variant="contained" component={RouterLink} to="/register">
                Get started
              </Button>
            </Stack>
          </Stack>
        </Container>
      </Box>
      <Container maxWidth="lg" sx={{ pb: { xs: 8, sm: 16 } }}>
        <Typography
          component="h2"
          variant="h4"
          sx={{ fontWeight: 600, textAlign: "center", mb: 4 }}
        >
          How it works
        </Typography>
        <Stack direction={{ xs: "column", md: "row" }} spacing={3}>
          {steps.map((step) => (
            <Card
              key={step.title}
              variant="outlined"
              sx={{ flex: 1, p: 3, opacity: step.coming ? 0.6 : 1 }}
            >
              <Box sx={{ color: "primary.main", mb: 1.5 }}>{step.icon}</Box>
              <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
                <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
                  {step.title}
                </Typography>
                {step.coming ? <Chip size="small" label="Coming" /> : null}
              </Stack>
              <Box sx={{ mt: 1 }} />
              <Typography variant="body2" color="text.secondary">
                {step.description}
              </Typography>
            </Card>
          ))}
        </Stack>
        <Typography
          component="h2"
          variant="h4"
          sx={{ fontWeight: 600, textAlign: "center", mt: { xs: 8, sm: 12 }, mb: 4 }}
        >
          Built for your team
        </Typography>
        <Stack direction={{ xs: "column", md: "row" }} spacing={3}>
          {values.map((value) => (
            <Card key={value.title} variant="outlined" sx={{ flex: 1, p: 3 }}>
              <Box sx={{ color: "primary.main", mb: 1.5 }}>{value.icon}</Box>
              <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
                {value.title}
              </Typography>
              <Box sx={{ mt: 1 }} />
              <Typography variant="body2" color="text.secondary">
                {value.description}
              </Typography>
            </Card>
          ))}
        </Stack>
      </Container>
    </MarketingFrame>
  );
}
