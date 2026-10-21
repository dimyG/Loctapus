import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { Link, Route, Routes, useLocation } from "react-router";
import { beforeEach, describe, expect, it } from "vitest";
import { initialRootState } from "../../app/store";
import { server } from "../../test/server";
import { renderWithProviders } from "../../test/test-utils";
import type { Project } from "../projects/projectsApi";
import { useGetUploadsQuery } from "../uploads/uploadsApi";
import type { Upload } from "../uploads/uploadsApi";
import ChatLanding from "./ChatLanding";

const authed = () => ({
  ...initialRootState(),
  auth: {
    token: "t-1",
    user: { id: "u-1", email: "user@example.test" },
    status: "idle" as const,
  },
});

// Deliberately oldest-first, so the resolver's newest-first sort is exercised.
const projectP1: Project = {
  id: "p-1",
  name: "Default",
  is_public: false,
  created_at: "2026-10-21T10:00:00Z",
};
const projectP2: Project = {
  id: "p-2",
  name: "Research",
  is_public: false,
  created_at: "2026-10-21T11:00:00Z",
};

const queuedP1: Upload = {
  id: "s-1",
  project_id: "p-1",
  status: "queued",
  filename: "brief.pdf",
  created_at: "2026-10-12T10:00:00Z",
};
const readyP1: Upload = {
  ...queuedP1,
  id: "s-2",
  status: "ready",
  filename: "report.docx",
  created_at: "2026-10-11T10:00:00Z",
};
const queuedP2: Upload = {
  id: "s-9",
  project_id: "p-2",
  status: "queued",
  filename: "notes.pdf",
  created_at: "2026-10-12T10:00:00Z",
};
const readyP2: Upload = {
  ...queuedP2,
  id: "s-8",
  status: "ready",
  filename: "paper.pdf",
  created_at: "2026-10-11T10:00:00Z",
};

/** Renders the current pathname so redirects are asserted on the URL itself. */
function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}</div>;
}

/** Primes the uploads cache for p-1 and links into the resolver. */
function PrimeCache() {
  const { data } = useGetUploadsQuery("p-1");
  return (
    <>
      {data?.map((upload) => (
        <span key={upload.id}>{upload.filename}</span>
      ))}
      <Link to="/app">Continue</Link>
    </>
  );
}

/** Renders the resolver behind its priming route and a catch-all location probe. */
function renderLanding(route = "/app") {
  return renderWithProviders(
    <Routes>
      <Route path="/prime" element={<PrimeCache />} />
      <Route path="/app" element={<ChatLanding />} />
      <Route path="*" element={<LocationProbe />} />
    </Routes>,
    { preloadedState: authed(), route },
  );
}

/** Overrides the projects list and both projects' uploads in one call. */
function projectsAndUploads(p1: Upload[], p2: Upload[]) {
  server.use(
    http.get("*/api/projects", () => HttpResponse.json([projectP1, projectP2])),
    http.get("*/api/projects/p-1/uploads", () => HttpResponse.json(p1)),
    http.get("*/api/projects/p-2/uploads", () => HttpResponse.json(p2)),
  );
}

describe("ChatLanding", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("redirects to the newest chattable project's chat", async () => {
    projectsAndUploads([queuedP1, readyP1], [queuedP2, readyP2]);
    renderLanding();
    await waitFor(() => {
      expect(screen.getByTestId("location")).toHaveTextContent("/projects/p-2/chat");
    });
  });

  it("skips processing projects and lands on the older chattable one", async () => {
    projectsAndUploads([queuedP1, readyP1], [queuedP2]);
    renderLanding();
    await waitFor(() => {
      expect(screen.getByTestId("location")).toHaveTextContent("/projects/p-1/chat");
    });
  });

  it("falls back to the latest project's sources when none are chattable", async () => {
    projectsAndUploads([queuedP1], [queuedP2]);
    renderLanding();
    await waitFor(() => {
      expect(screen.getByTestId("location")).toHaveTextContent("/projects/p-2/sources");
    });
  });

  it("treats a failing uploads fetch as not chattable and continues the walk", async () => {
    server.use(
      http.get("*/api/projects", () => HttpResponse.json([projectP1, projectP2])),
      http.get("*/api/projects/p-1/uploads", () => HttpResponse.json([queuedP1, readyP1])),
      http.get("*/api/projects/p-2/uploads", () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );
    renderLanding();
    // The newest project's failure must not end the walk: p-1 is chattable.
    await waitFor(() => {
      expect(screen.getByTestId("location")).toHaveTextContent("/projects/p-1/chat");
    });
  });

  it("treats a failing uploads fetch as not chattable and never hangs", async () => {
    server.use(
      http.get("*/api/projects", () => HttpResponse.json([projectP1, projectP2])),
      http.get("*/api/projects/p-1/uploads", () => HttpResponse.json([queuedP1])),
      http.get("*/api/projects/p-2/uploads", () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );
    renderLanding();
    // Every stop is non-chattable, so the walk must still conclude on the fallback.
    await waitFor(() => {
      expect(screen.getByTestId("location")).toHaveTextContent("/projects/p-2/sources");
    });
  });

  it("renders the projects list when there are no projects", async () => {
    server.use(http.get("*/api/projects", () => HttpResponse.json([])));
    renderLanding();
    await waitFor(() => {
      expect(screen.getByTestId("location")).toHaveTextContent("/projects");
    });
  });

  it("refetches stale cached statuses", async () => {
    // p-2 must be non-chattable here: the walk stops at the first chattable
    // project, so a chattable p-2 would never reach the stale p-1 entry.
    projectsAndUploads([queuedP1], [queuedP2]);
    renderLanding("/prime");
    // Wait until the priming subscription has cached the queued list.
    expect(await screen.findByText("brief.pdf")).toBeInTheDocument();
    // The statuses went stale after priming: only a forced refetch sees the ready row.
    server.use(http.get("*/api/projects/p-1/uploads", () => HttpResponse.json([readyP1])));
    await userEvent.setup().click(screen.getByRole("link", { name: "Continue" }));
    await waitFor(() => {
      expect(screen.getByTestId("location")).toHaveTextContent("/projects/p-1/chat");
    });
  });
});
