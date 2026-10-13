import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { initialRootState } from "../../app/store";
import { renderWithProviders } from "../../test/test-utils";
import { server } from "../../test/server";
import ProjectsPage from "./ProjectsPage";

const authed = () => ({
  ...initialRootState(),
  auth: {
    token: "t-1",
    user: { id: "u-1", email: "user@example.test" },
    status: "idle" as const,
  },
});

function renderProjects() {
  return renderWithProviders(<ProjectsPage />, { preloadedState: authed() });
}

const projectRows = [
  { id: "p-1", name: "Default", is_public: false, created_at: "2026-10-09T10:00:00Z" },
  { id: "p-2", name: "Research notes", is_public: true, created_at: "2026-10-08T10:00:00Z" },
];

describe("ProjectsPage", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("renders project rows with name, visibility, and created date", async () => {
    server.use(http.get("*/projects", () => HttpResponse.json(projectRows)));
    renderProjects();
    expect(await screen.findByText("Research notes")).toBeInTheDocument();
    expect(screen.getByText("Default")).toBeInTheDocument();
    expect(screen.getByText("Public")).toBeInTheDocument();
    expect(screen.getByText("Private")).toBeInTheDocument();
    expect(
      screen.getByText(new Date("2026-10-09T10:00:00Z").toLocaleDateString()),
    ).toBeInTheDocument();
  });

  it("links project names to their project pages", async () => {
    server.use(http.get("*/projects", () => HttpResponse.json(projectRows)));
    renderProjects();
    const link = await screen.findByRole("link", { name: "Research notes" });
    expect(link).toHaveAttribute("href", "/projects/p-2");
    expect(screen.getByRole("link", { name: "Default" })).toHaveAttribute("href", "/projects/p-1");
  });

  it("shows skeletons while loading", async () => {
    let resolveRequest: (() => void) | undefined;
    server.use(
      http.get("*/projects", async () => {
        await new Promise<void>((resolve) => {
          resolveRequest = resolve;
        });
        return HttpResponse.json([]);
      }),
    );
    renderProjects();
    await vi
      .waitFor(() => {
        expect(screen.getAllByTestId("skeleton-row")).toHaveLength(5);
      })
      .then(() => undefined)
      .catch(() => {
        throw new Error("skeleton rows never rendered");
      });
    expect(screen.queryByText("No projects yet")).not.toBeInTheDocument();
    resolveRequest?.();
  });

  it("shows the empty state when there are no projects", async () => {
    renderProjects();
    expect(await screen.findByText("No projects yet")).toBeInTheDocument();
  });

  it("shows a retryable error card when the API is unreachable", async () => {
    let failing = true;
    server.use(
      http.get("*/projects", () =>
        failing ? HttpResponse.error() : HttpResponse.json(projectRows),
      ),
    );
    renderProjects();
    expect(await screen.findByText("Could not load projects.")).toBeInTheDocument();
    const retry = screen.getByRole("button", { name: "Try again" });
    expect(retry).toBeInTheDocument();
    failing = false;
    await userEvent.setup().click(retry);
    expect(await screen.findByText("Research notes")).toBeInTheDocument();
    expect(screen.queryByText("Could not load projects.")).not.toBeInTheDocument();
  });
});
