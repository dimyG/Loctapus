import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { Navigate } from "react-router";
import { useAppSelector } from "../../app/hooks";
import { selectUser } from "../auth/authSlice";
import MarketingLayout from "../../layouts/MarketingLayout";

const steps = [
  {
    title: "Create a project",
    description: "Group your documents in one place and share them with a team.",
  },
  {
    title: "Upload documents",
    description: "Add PDFs and text files; every file is stored and tracked.",
  },
  {
    title: "Ask questions",
    description: "Ask in plain language and get answers that cite the source.",
  },
];

/** The public landing page; signed-in visitors are redirected to their projects. */
export default function LandingPage() {
  // The hydrated user, not the stored token, drives the redirect: a visitor
  // whose token has gone stale must stay on the public landing instead of
  // being bounced to /login by the guarded route.
  const user = useAppSelector(selectUser);
  if (user !== null) {
    return <Navigate to="/projects" replace />;
  }

  return (
    <MarketingLayout>
      <Stack sx={{ textAlign: "center", py: { xs: 6, md: 10 } }} spacing={3}>
        <Typography
          component="h1"
          variant="h3"
          sx={{ fontWeight: 600, maxWidth: "sm", mx: "auto" }}
        >
          Your documents, searchable by meaning - upload, ask, get grounded answers
        </Typography>
        <Typography
          variant="h6"
          color="text.secondary"
          sx={{ maxWidth: "sm", mx: "auto", fontWeight: 400 }}
        >
          A private workspace where your team stores its documents and asks questions in everyday
          language.
        </Typography>
        <Stack direction="row" spacing={2} sx={{ justifyContent: "center" }}>
          <Button variant="contained" component="a" href="/register">
            Get started
          </Button>
          <Button variant="outlined" component="a" href="/login">
            Sign in
          </Button>
        </Stack>
      </Stack>
      <Stack direction={{ xs: "column", md: "row" }} spacing={3}>
        {steps.map((step) => (
          <Card key={step.title} variant="outlined" sx={{ flex: 1, p: 3 }}>
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
    </MarketingLayout>
  );
}
