import AccountTreeRoundedIcon from "@mui/icons-material/AccountTreeRounded";
import AddToDriveRoundedIcon from "@mui/icons-material/AddToDriveRounded";
import ApiRoundedIcon from "@mui/icons-material/ApiRounded";
import ArrowDownwardRoundedIcon from "@mui/icons-material/ArrowDownwardRounded";
import ArrowForwardRoundedIcon from "@mui/icons-material/ArrowForwardRounded";
import AutoAwesomeRoundedIcon from "@mui/icons-material/AutoAwesomeRounded";
import BuildRoundedIcon from "@mui/icons-material/BuildRounded";
import CheckCircleRoundedIcon from "@mui/icons-material/CheckCircleRounded";
import CloudDoneRoundedIcon from "@mui/icons-material/CloudDoneRounded";
import CloudUploadRoundedIcon from "@mui/icons-material/CloudUploadRounded";
import ForumRoundedIcon from "@mui/icons-material/ForumRounded";
import GavelRoundedIcon from "@mui/icons-material/GavelRounded";
import GroupsRoundedIcon from "@mui/icons-material/GroupsRounded";
import HubRoundedIcon from "@mui/icons-material/HubRounded";
import LanguageRoundedIcon from "@mui/icons-material/LanguageRounded";
import LockPersonRoundedIcon from "@mui/icons-material/LockPersonRounded";
import LockRoundedIcon from "@mui/icons-material/LockRounded";
import PictureAsPdfRoundedIcon from "@mui/icons-material/PictureAsPdfRounded";
import RocketLaunchRoundedIcon from "@mui/icons-material/RocketLaunchRounded";
import SearchRoundedIcon from "@mui/icons-material/SearchRounded";
import SmartToyRoundedIcon from "@mui/icons-material/SmartToyRounded";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import Chip from "@mui/material/Chip";
import Container from "@mui/material/Container";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { keyframes, type Theme } from "@mui/material/styles";
import type { ReactNode } from "react";
import { Link as RouterLink, Navigate } from "react-router";
import { useAppSelector } from "../../app/hooks";
import MarketingFrame from "../../layouts/MarketingFrame";
import { selectAuthStatus, selectUser } from "../auth/authSlice";

/** A source or channel tag on a how-it-works step. */
type Tag = { label: string; coming: boolean };

const steps: { icon: ReactNode; title: string; description: string; tags: Tag[] }[] = [
  {
    icon: <CloudUploadRoundedIcon />,
    title: "Connect your sources",
    description:
      "Bring in your documents from wherever they live. Upload files today, with cloud drives and websites on the way.",
    tags: [
      { label: "PDF & DOCX", coming: false },
      { label: "Google Drive", coming: true },
      { label: "Websites", coming: true },
    ],
  },
  {
    icon: <AutoAwesomeRoundedIcon />,
    title: "Loctapus organizes it",
    description:
      "Every document is parsed, split into passages, and indexed automatically into one searchable knowledge base. Answers cite the passages they come from.",
    tags: [
      { label: "Parsing", coming: false },
      { label: "Hybrid search", coming: false },
      { label: "Cited answers", coming: false },
    ],
  },
  {
    icon: <RocketLaunchRoundedIcon />,
    title: "Make it available",
    description:
      "Put your knowledge to work where it is needed: in our web chat, your applications, your AI agents, or any other channel your business uses.",
    tags: [
      { label: "Web chat", coming: false },
      { label: "API", coming: true },
      { label: "MCP", coming: true },
    ],
  },
];

const teamFeatures = [
  {
    icon: <AccountTreeRoundedIcon />,
    title: "Organized the way you work",
    description:
      "Workspaces hold your teams and projects. Each project gathers its own sources, so every knowledge base stays focused on the work it serves.",
    coming: false,
  },
  {
    icon: <LockPersonRoundedIcon />,
    title: "Access only where it's granted",
    description:
      "Teams are given access to specific projects. Members see and query only those projects, and answers never draw on documents they cannot access.",
    coming: false,
  },
  {
    icon: <ForumRoundedIcon />,
    title: "Meet your customers where they are",
    description:
      "Add a chat to your documentation page, your app, or the messaging tools your customers already use, like Slack or Microsoft Teams, all backed by the same knowledge base.",
    coming: true,
  },
  {
    icon: <CloudDoneRoundedIcon />,
    title: "Always in sync, fully managed",
    description:
      "Sources sync automatically, so answers always reflect the latest version. Processing recovers from failures on its own, and there is no infrastructure for you to run.",
    coming: true,
  },
];

const useCases = [
  {
    eyebrow: "Customer support",
    title: "Self-service support on your docs site",
    description:
      "A hardware company keeps its manuals in Google Drive and its guides on a public documentation website. It connects both as sources of one project, and Loctapus keeps them indexed and in sync. A chat widget on the docs page lets customers ask questions and get answers that cite the exact guide.",
    benefits: [
      "Fewer tickets for questions the docs already answer",
      "Answers always reflect the latest manuals and guides",
      "Every answer links back to its source",
    ],
    tags: ["Sources: Google Drive, Website", "Interface: Chat widget"],
    illustration: <DocsChatIllustration />,
  },
  {
    eyebrow: "AI agents",
    title: "Hundreds of PDFs, ready for your agents",
    description:
      "A legal team uploads hundreds of contracts, policies, and court rulings as PDFs. Loctapus parses and indexes them once, then exposes the knowledge base through MCP, so the team's own AI agents query it directly.",
    benefits: [
      "One knowledge base shared by every agent",
      "No custom retrieval pipeline to build or maintain",
      "Agents work from cited passages instead of guesses",
    ],
    tags: ["Source: PDF uploads", "Interface: MCP"],
    illustration: <PdfAgentsIllustration />,
  },
  {
    eyebrow: "In-app answers",
    title: "Put the knowledge base inside your app",
    description:
      "A field-service company uploads its equipment manuals and publishes service bulletins on its website, both as sources of one project. Its technicians' mobile app calls the Loctapus API, so a technician on site types an error code and gets the fix, with a link to the right manual page, without leaving the app.",
    benefits: [
      "AI answers in your product without building a retrieval pipeline",
      "New service bulletins reach the app as soon as they are published",
      "Every answer carries its source for your app to show",
    ],
    tags: ["Sources: PDF uploads, Website", "Interface: API"],
    illustration: <InAppIllustration />,
  },
  {
    eyebrow: "Team-scoped projects",
    title: "A private knowledge base for every team",
    description:
      "A growing company keeps its HR policies, engineering runbooks, and sales playbooks in one workspace, each in its own project. Every team is granted access only to its own project, so an engineer asking about on-call gets answers from the runbooks and never from HR files. Employees ask in the web chat, Slack, or Microsoft Teams, and the same access rules apply everywhere.",
    benefits: [
      "Each team's knowledge stays with the team that owns it",
      "Answers never draw on documents a member cannot access",
      "Focused projects keep every team's answers on topic",
    ],
    tags: ["Sources: Google Drive, uploads", "Interface: Web chat, Slack, Teams"],
    illustration: <TeamProjectsIllustration />,
  },
];

const pulse = keyframes`
  0% { box-shadow: 0 0 0 0 currentColor; }
  70% { box-shadow: 0 0 0 6px transparent; }
  100% { box-shadow: 0 0 0 0 transparent; }
`;

/** The small "Coming soon" marker shared by cards and use cases. */
function ComingSoonChip() {
  return <Chip size="small" label="Coming soon" />;
}

/**
 * A centered section heading with a short supporting line.
 *
 * @param {string} title - The section's h2 text.
 * @param {string} subtitle - One sentence under the heading.
 */
function SectionHeading({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <Stack spacing={1.5} sx={{ alignItems: "center", textAlign: "center", mb: { xs: 4, sm: 6 } }}>
      <Typography component="h2" variant="h4" sx={{ fontWeight: 600 }}>
        {title}
      </Typography>
      <Typography color="text.secondary" sx={{ maxWidth: 560 }}>
        {subtitle}
      </Typography>
    </Stack>
  );
}

/** A tinted rounded square holding a feature icon. */
function IconBadge({ children }: { children: ReactNode }) {
  return (
    <Box
      sx={(theme) => ({
        width: 44,
        height: 44,
        flexShrink: 0,
        borderRadius: 2,
        display: "grid",
        placeItems: "center",
        color: "primary.main",
        bgcolor: "hsla(210, 100%, 60%, 0.1)",
        ...theme.applyStyles("dark", { bgcolor: "hsla(210, 100%, 60%, 0.16)" }),
      })}
    >
      {children}
    </Box>
  );
}

/** The hero: the "Under development" label, the headline, and the single CTA. */
function Hero() {
  return (
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
          <Chip
            variant="outlined"
            size="small"
            label="Under development"
            icon={
              <Box
                component="span"
                sx={{
                  width: 8,
                  height: 8,
                  borderRadius: "50%",
                  color: "warning.main",
                  bgcolor: "warning.main",
                  animation: `${pulse} 2s infinite`,
                  "@media (prefers-reduced-motion: reduce)": { animation: "none" },
                }}
              />
            }
            sx={{ mb: 1, px: 0.5, bgcolor: "background.paper", fontWeight: 500 }}
          />
          <Typography
            component="h1"
            sx={{
              fontSize: "clamp(2.5rem, 8vw, 3.5rem)",
              fontWeight: 600,
              textAlign: "center",
              lineHeight: 1.15,
              textWrap: "balance",
            }}
          >
            <Box component="span" sx={{ display: "block", color: "primary.main" }}>
              Loctapus
            </Box>{" "}
            Bring your knowledge base to life
          </Typography>
          <Typography
            variant="h6"
            color="text.secondary"
            sx={{ fontWeight: 400, textAlign: "center", width: { sm: "100%", md: "85%" } }}
          >
            Combine knowledge from multiple sources into a unified, searchable knowledge base and
            make it accessible to applications, AI agents, and users through web chat, APIs, and
            MCP.
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
  );
}

/** The three numbered how-it-works steps, each with its source or channel tags. */
function HowItWorks() {
  return (
    <Box component="section" sx={{ pb: { xs: 10, sm: 14 } }}>
      <SectionHeading
        title="How it works"
        subtitle="From scattered documents to answers your users can trust, in three steps."
      />
      <Box
        sx={{
          display: "grid",
          gap: 3,
          gridTemplateColumns: { xs: "1fr", md: "repeat(3, 1fr)" },
        }}
      >
        {steps.map((step, index) => (
          <Card
            key={step.title}
            variant="outlined"
            sx={{ p: 3, display: "flex", flexDirection: "column", gap: 2 }}
          >
            <Stack direction="row" sx={{ alignItems: "center", justifyContent: "space-between" }}>
              <IconBadge>{step.icon}</IconBadge>
              <Typography
                aria-hidden
                sx={{ fontSize: "2rem", fontWeight: 700, lineHeight: 1, color: "divider" }}
              >
                {String(index + 1).padStart(2, "0")}
              </Typography>
            </Stack>
            <Typography component="h3" variant="subtitle1" sx={{ fontWeight: 600 }}>
              {step.title}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ flexGrow: 1 }}>
              {step.description}
            </Typography>
            <Stack direction="row" useFlexGap sx={{ flexWrap: "wrap", gap: 1 }}>
              {step.tags.map((tag) => (
                <Chip
                  key={tag.label}
                  size="small"
                  variant="outlined"
                  color={tag.coming ? "default" : "primary"}
                  label={tag.coming ? `${tag.label} · Coming soon` : tag.label}
                  sx={tag.coming ? { color: "text.secondary", borderStyle: "dashed" } : undefined}
                />
              ))}
            </Stack>
          </Card>
        ))}
      </Box>
    </Box>
  );
}

/** The four team features in a two-by-two grid. */
function BuiltForTeams() {
  return (
    <Box component="section" sx={{ pb: { xs: 10, sm: 14 } }}>
      <SectionHeading
        title="Built for teams"
        subtitle="Structure, access control, and reliability for organizations of any size."
      />
      <Box
        sx={{
          display: "grid",
          gap: 3,
          gridTemplateColumns: { xs: "1fr", md: "repeat(2, 1fr)" },
        }}
      >
        {teamFeatures.map((feature) => (
          <Card
            key={feature.title}
            variant="outlined"
            sx={{ p: 3, display: "flex", gap: 2.5, alignItems: "flex-start" }}
          >
            <IconBadge>{feature.icon}</IconBadge>
            <Box>
              <Stack
                direction="row"
                useFlexGap
                sx={{ alignItems: "center", flexWrap: "wrap", gap: 1, mb: 1 }}
              >
                <Typography component="h3" variant="subtitle1" sx={{ fontWeight: 600 }}>
                  {feature.title}
                </Typography>
                {feature.coming ? <ComingSoonChip /> : null}
              </Stack>
              <Typography variant="body2" color="text.secondary">
                {feature.description}
              </Typography>
            </Box>
          </Card>
        ))}
      </Box>
    </Box>
  );
}

/** The use cases as alternating illustration and story rows. */
function UseCases() {
  return (
    <Box component="section" sx={{ pb: { xs: 8, sm: 16 } }}>
      <SectionHeading
        title="Use cases"
        subtitle="Examples of how teams can put their knowledge to work with Loctapus."
      />
      <Stack spacing={{ xs: 8, md: 10 }}>
        {useCases.map((useCase, index) => (
          <Box
            key={useCase.title}
            sx={{
              display: "grid",
              gap: { xs: 4, lg: 8 },
              alignItems: "center",
              // The illustrations need about 650px, so rows sit side by side only
              // from lg, with a wider illustration column; minmax(0, ...) stops the
              // content from stretching its column past the 3:2 split.
              gridTemplateColumns: {
                xs: "1fr",
                lg:
                  index % 2 === 0
                    ? "minmax(0, 3fr) minmax(0, 2fr)"
                    : "minmax(0, 2fr) minmax(0, 3fr)",
              },
            }}
          >
            {/* Stacked, the illustration always leads; side by side, the rows alternate. */}
            <Box sx={{ order: { xs: 0, lg: index % 2 === 0 ? 0 : 1 } }}>{useCase.illustration}</Box>
            <Box>
              <Stack direction="row" spacing={1.5} sx={{ alignItems: "center", mb: 0.5 }}>
                <Typography variant="overline" color="primary" sx={{ fontWeight: 600 }}>
                  {useCase.eyebrow}
                </Typography>
                <ComingSoonChip />
              </Stack>
              <Typography component="h3" variant="h5" sx={{ fontWeight: 600, mb: 2 }}>
                {useCase.title}
              </Typography>
              <Typography color="text.secondary" sx={{ mb: 3 }}>
                {useCase.description}
              </Typography>
              <Stack component="ul" spacing={1.25} sx={{ p: 0, m: 0, mb: 3, listStyle: "none" }}>
                {useCase.benefits.map((benefit) => (
                  <Stack
                    component="li"
                    key={benefit}
                    direction="row"
                    spacing={1.25}
                    sx={{ alignItems: "flex-start" }}
                  >
                    <CheckCircleRoundedIcon
                      fontSize="small"
                      sx={{ color: "primary.main", mt: "2px" }}
                    />
                    <Typography variant="body2">{benefit}</Typography>
                  </Stack>
                ))}
              </Stack>
              <Stack direction="row" useFlexGap sx={{ flexWrap: "wrap", gap: 1 }}>
                {useCase.tags.map((tag) => (
                  <Chip key={tag} size="small" variant="outlined" label={tag} />
                ))}
              </Stack>
            </Box>
          </Box>
        ))}
      </Stack>
    </Box>
  );
}

/**
 * The tinted canvas behind each use-case illustration. Illustrations are
 * decorative, so the canvas hides them from assistive technology.
 */
function IllustrationCanvas({ children }: { children: ReactNode }) {
  return (
    <Box
      aria-hidden
      sx={(theme) => ({
        borderRadius: 3,
        border: "1px solid",
        borderColor: "divider",
        p: { xs: 2.5, md: 3 },
        minHeight: { lg: 340 },
        display: "flex",
        flexDirection: { xs: "column", md: "row" },
        alignItems: "center",
        justifyContent: "center",
        gap: 1.5,
        backgroundImage:
          "radial-gradient(ellipse 90% 70% at 50% 0%, hsl(210, 100%, 95%), hsl(220, 30%, 98%))",
        ...theme.applyStyles("dark", {
          backgroundImage:
            "radial-gradient(ellipse 90% 70% at 50% 0%, hsl(210, 100%, 14%), hsl(220, 30%, 7%))",
        }),
      })}
    >
      {children}
    </Box>
  );
}

/** An arrow between illustration stages: right on wide screens, down on narrow ones. */
function FlowArrow() {
  return (
    <Box sx={{ color: "primary.main", display: "flex", opacity: 0.7 }}>
      <ArrowForwardRoundedIcon sx={{ display: { xs: "none", md: "block" } }} />
      <ArrowDownwardRoundedIcon sx={{ display: { xs: "block", md: "none" } }} />
    </Box>
  );
}

/**
 * A small labelled tile in an illustration.
 *
 * @param {ReactNode} icon - The tile's icon.
 * @param {string} label - The caption under the icon.
 */
function Tile({ icon, label }: { icon: ReactNode; label: string }) {
  return (
    <Paper
      variant="outlined"
      sx={{
        px: 1.5,
        py: 1,
        display: "flex",
        alignItems: "center",
        gap: 1,
        borderRadius: 2,
        whiteSpace: "nowrap",
      }}
    >
      {icon}
      <Typography variant="caption" sx={{ fontWeight: 600 }}>
        {label}
      </Typography>
    </Paper>
  );
}

/**
 * The Loctapus hub the source-to-interface illustrations flow through.
 *
 * @param {ReactNode} footer - An optional element under the logo, such as the MCP tag.
 */
function Hub({ footer }: { footer?: ReactNode }) {
  return (
    <Paper
      variant="outlined"
      sx={{
        p: 1.5,
        borderRadius: 3,
        borderColor: "primary.main",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 0.75,
        boxShadow: "0 0 0 6px hsla(210, 100%, 60%, 0.12)",
      }}
    >
      <img src="/logo.png" alt="" width={40} height={40} />
      <Typography variant="caption" sx={{ fontWeight: 600 }}>
        Loctapus
      </Typography>
      {footer}
    </Paper>
  );
}

/** The PDF red, lifted in dark mode where the main error red reads too dim. */
function pdfIconSx(theme: Theme) {
  return { color: "error.main", ...theme.applyStyles("dark", { color: "error.light" }) };
}

/** A grey placeholder bar standing in for a line of page text. */
function TextLine({ width }: { width: string }) {
  return <Box sx={{ height: 6, width, borderRadius: 3, bgcolor: "action.hover" }} />;
}

/**
 * The filled title strip of an illustration's chat window.
 *
 * @param {ReactNode} children - The title content.
 */
function ChatHeader({ children }: { children: ReactNode }) {
  return (
    <Box
      sx={{
        px: 1,
        py: 0.5,
        display: "flex",
        alignItems: "center",
        gap: 0.5,
        bgcolor: "primary.main",
        color: "primary.contrastText",
        fontSize: "0.65rem",
        fontWeight: 600,
      }}
    >
      {children}
    </Box>
  );
}

/** The highlighted source line closing an assistant bubble. */
function SourceLine({ children }: { children: ReactNode }) {
  return (
    <Box
      component="span"
      sx={{ display: "block", mt: 0.5, color: "primary.main", fontWeight: 600 }}
    >
      {children}
    </Box>
  );
}

/**
 * A chat bubble inside an illustration's chat window.
 *
 * @param {boolean} fromUser - Whether the user (right, filled) or the assistant (left) speaks.
 * @param {ReactNode} children - The bubble content.
 */
function Bubble({ fromUser, children }: { fromUser: boolean; children: ReactNode }) {
  return (
    <Box
      sx={{
        alignSelf: fromUser ? "flex-end" : "flex-start",
        maxWidth: "88%",
        px: 1,
        py: 0.75,
        borderRadius: 1.5,
        fontSize: "0.65rem",
        lineHeight: 1.4,
        bgcolor: fromUser ? "primary.main" : "action.hover",
        color: fromUser ? "primary.contrastText" : "text.primary",
      }}
    >
      {children}
    </Box>
  );
}

/** Google Drive and a docs website flow into Loctapus and out to a chat widget on the docs page. */
function DocsChatIllustration() {
  return (
    <IllustrationCanvas>
      <Stack spacing={1.5}>
        <Tile icon={<AddToDriveRoundedIcon color="success" />} label="Google Drive" />
        <Tile icon={<LanguageRoundedIcon color="primary" />} label="docs.elvenmagic.com" />
      </Stack>
      <FlowArrow />
      <Hub />
      <FlowArrow />
      <Paper
        variant="outlined"
        sx={{ width: 230, borderRadius: 2, overflow: "hidden", position: "relative" }}
      >
        <Stack
          direction="row"
          spacing={0.5}
          sx={{ alignItems: "center", px: 1, py: 0.75, borderBottom: 1, borderColor: "divider" }}
        >
          {["error.light", "warning.light", "success.light"].map((color) => (
            <Box key={color} sx={{ width: 7, height: 7, borderRadius: "50%", bgcolor: color }} />
          ))}
          <Box
            sx={{
              ml: 1,
              flexGrow: 1,
              px: 1,
              borderRadius: 1,
              bgcolor: "action.hover",
              fontSize: "0.6rem",
              color: "text.secondary",
            }}
          >
            docs.elvenmagic.com
          </Box>
        </Stack>
        <Stack spacing={0.75} sx={{ p: 1.5, pb: 17 }}>
          <Box sx={{ height: 9, width: "55%", borderRadius: 3, bgcolor: "text.disabled" }} />
          <TextLine width="90%" />
          <TextLine width="80%" />
          <TextLine width="85%" />
          <TextLine width="40%" />
        </Stack>
        <Paper
          elevation={4}
          sx={{
            position: "absolute",
            right: 8,
            bottom: 8,
            width: 170,
            borderRadius: 2,
            overflow: "hidden",
          }}
        >
          <ChatHeader>Ask Elven Magic docs</ChatHeader>
          <Stack spacing={0.75} sx={{ p: 1 }}>
            <Bubble fromUser>How do I reset my device?</Bubble>
            <Bubble fromUser={false}>
              Hold the power button for 10 seconds until the light blinks.
              <SourceLine>Source: Setup guide</SourceLine>
            </Bubble>
          </Stack>
        </Paper>
      </Paper>
    </IllustrationCanvas>
  );
}

/** A stack of PDFs flows into Loctapus, which serves several AI agents over MCP. */
function PdfAgentsIllustration() {
  const agents = [
    { icon: <GavelRoundedIcon color="primary" />, label: "Contract review agent" },
    { icon: <SearchRoundedIcon color="primary" />, label: "Research agent" },
    { icon: <SmartToyRoundedIcon color="primary" />, label: "Internal copilot" },
  ];
  return (
    <IllustrationCanvas>
      <Box sx={{ position: "relative", width: 92, height: 112 }}>
        {[16, 8, 0].map((offset) => (
          <Paper
            key={offset}
            variant="outlined"
            sx={{
              position: "absolute",
              top: offset,
              left: 16 - offset,
              width: 68,
              height: 86,
              borderRadius: 1.5,
              display: "grid",
              placeItems: "center",
            }}
          >
            {offset === 0 ? <PictureAsPdfRoundedIcon sx={[pdfIconSx, { fontSize: 34 }]} /> : null}
          </Paper>
        ))}
        <Chip
          size="small"
          color="primary"
          label="+480 PDFs"
          sx={{ position: "absolute", bottom: 0, right: 0, fontWeight: 600 }}
        />
      </Box>
      <FlowArrow />
      <Hub
        footer={
          <Chip
            size="small"
            variant="outlined"
            color="primary"
            icon={<HubRoundedIcon />}
            label="MCP"
            sx={{ fontWeight: 600 }}
          />
        }
      />
      <FlowArrow />
      <Stack spacing={1.5}>
        {agents.map((agent) => (
          <Tile key={agent.label} icon={agent.icon} label={agent.label} />
        ))}
      </Stack>
    </IllustrationCanvas>
  );
}

/** A technician's phone app showing an answer fetched from the Loctapus API. */
function PhoneMock() {
  return (
    <Paper variant="outlined" sx={{ width: 150, flexShrink: 0, borderRadius: 4, p: 0.75 }}>
      <Box
        sx={{ mx: "auto", mb: 0.75, width: 36, height: 4, borderRadius: 2, bgcolor: "divider" }}
      />
      <Box
        sx={{
          minHeight: 220,
          borderRadius: 3,
          overflow: "hidden",
          border: 1,
          borderColor: "divider",
        }}
      >
        <ChatHeader>
          <BuildRoundedIcon sx={{ fontSize: 12 }} />
          FieldFix
        </ChatHeader>
        <Stack spacing={0.75} sx={{ p: 1 }}>
          <Box
            sx={{
              px: 0.75,
              py: 0.5,
              display: "flex",
              alignItems: "center",
              gap: 0.5,
              border: 1,
              borderColor: "divider",
              borderRadius: 1.5,
              fontSize: "0.6rem",
              color: "text.secondary",
            }}
          >
            <SearchRoundedIcon sx={{ fontSize: 12 }} />
            Error E42 on X200 pump
          </Box>
          <Bubble fromUser={false}>
            Reset the pressure sensor, then bleed the inlet valve.
            <SourceLine>Source: X200 manual, p. 34</SourceLine>
          </Bubble>
          <TextLine width="85%" />
          <TextLine width="60%" />
        </Stack>
      </Box>
    </Paper>
  );
}

/** Manuals and service bulletins flow into Loctapus, which answers a technician's app over the API. */
function InAppIllustration() {
  return (
    <IllustrationCanvas>
      <Stack spacing={1.5}>
        <Tile icon={<PictureAsPdfRoundedIcon sx={pdfIconSx} />} label="Equipment manuals" />
        <Tile icon={<LanguageRoundedIcon color="primary" />} label="Service bulletins" />
      </Stack>
      <FlowArrow />
      <Hub
        footer={
          <Chip
            size="small"
            variant="outlined"
            color="primary"
            icon={<ApiRoundedIcon />}
            label="API"
            sx={{ fontWeight: 600 }}
          />
        }
      />
      <FlowArrow />
      <PhoneMock />
    </IllustrationCanvas>
  );
}

/**
 * One workspace whose projects are each granted to a single team. The
 * Engineering row is lit to match the chat, which searches only its project.
 */
function TeamProjectsIllustration() {
  const grants = [
    { team: "HR", project: "HR policies", active: false },
    { team: "Engineering", project: "Runbooks", active: true },
    { team: "Sales", project: "Playbooks", active: false },
  ];
  return (
    <IllustrationCanvas>
      <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 3 }}>
        <Stack direction="row" spacing={0.75} sx={{ alignItems: "center", mb: 1.5 }}>
          <img src="/logo.png" alt="" width={20} height={20} />
          <Typography variant="caption" sx={{ fontWeight: 600 }}>
            Company workspace
          </Typography>
        </Stack>
        <Stack spacing={1}>
          {grants.map((grant) => (
            <Stack
              key={grant.team}
              direction="row"
              spacing={0.75}
              sx={{ alignItems: "center", opacity: grant.active ? 1 : 0.5 }}
            >
              <Chip
                size="small"
                icon={<GroupsRoundedIcon />}
                label={grant.team}
                color={grant.active ? "primary" : "default"}
                sx={{ width: 104, justifyContent: "flex-start", fontWeight: 600 }}
              />
              <ArrowForwardRoundedIcon sx={{ fontSize: 14, color: "text.secondary" }} />
              <Tile
                icon={
                  <LockRoundedIcon
                    sx={{ fontSize: 16, color: grant.active ? "primary.main" : "text.secondary" }}
                  />
                }
                label={grant.project}
              />
            </Stack>
          ))}
        </Stack>
      </Paper>
      <FlowArrow />
      <Paper
        variant="outlined"
        sx={{ width: 160, flexShrink: 0, borderRadius: 2, overflow: "hidden" }}
      >
        <ChatHeader>
          <GroupsRoundedIcon sx={{ fontSize: 12 }} />
          Engineering chat
        </ChatHeader>
        <Stack spacing={0.75} sx={{ p: 1 }}>
          <Bubble fromUser>What is the on-call escalation path?</Bubble>
          <Bubble fromUser={false}>
            Page the secondary on-call after 15 minutes.
            <SourceLine>Source: Runbooks</SourceLine>
          </Bubble>
          <Box
            sx={{
              display: "flex",
              alignItems: "center",
              gap: 0.5,
              fontSize: "0.58rem",
              color: "text.secondary",
            }}
          >
            <LockRoundedIcon sx={{ fontSize: 10 }} />
            Searched Runbooks only
          </Box>
        </Stack>
      </Paper>
    </IllustrationCanvas>
  );
}

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
      <Hero />
      <Container maxWidth="lg">
        <HowItWorks />
        <BuiltForTeams />
        <UseCases />
      </Container>
    </MarketingFrame>
  );
}
