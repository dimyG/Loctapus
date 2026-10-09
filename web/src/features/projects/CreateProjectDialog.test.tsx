import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { initialRootState } from "../../app/store";
import { renderWithProviders } from "../../test/test-utils";
import { server } from "../../test/server";
import CreateProjectDialog from "./CreateProjectDialog";
import ProjectsPage from "./ProjectsPage";

const authed = () => ({
  ...initialRootState(),
  auth: {
    token: "t-1",
    user: { id: "u-1", email: "user@example.test" },
    status: "idle" as const,
  },
});

function renderDialog(onClose = () => undefined) {
  return renderWithProviders(<CreateProjectDialog open onClose={onClose} />, {
    preloadedState: authed(),
  });
}

function renderPage() {
  return renderWithProviders(<ProjectsPage />, { preloadedState: authed() });
}

/** Reads a MUI Select's hidden form input, which carries the selected value. */
function selectedValue(name: string): string | undefined {
  return document.querySelector<HTMLInputElement>(`input[name="${name}"]`)?.value;
}

/** Waits for the selects to auto-preselect the only workspace/team pair. */
async function waitForPreselection() {
  await vi.waitFor(() => {
    expect(selectedValue("workspace")).toBe("w-1");
    expect(selectedValue("team")).toBe("t-1");
  });
}

describe("CreateProjectDialog", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("populates workspace and team options and auto-preselects the only pair", async () => {
    renderDialog();
    await waitForPreselection();
    // Both selects display the fixture team/workspace name.
    expect(screen.getAllByText("Default")).toHaveLength(2);
  });

  it("posts { name, team_id } and the new project appears in the list", async () => {
    const state = {
      projects: [
        { id: "p-1", name: "Default", is_public: false, created_at: "2026-10-09T10:00:00Z" },
      ],
    };
    const posted: { name: string; team_id: string }[] = [];
    server.use(
      http.get("*/projects", () => HttpResponse.json(state.projects)),
      http.post("*/projects", async ({ request }) => {
        const body = (await request.json()) as { name: string; team_id: string };
        posted.push(body);
        const created = {
          id: "p-new",
          name: body.name,
          is_public: false,
          created_at: "2026-10-09T12:00:00Z",
        };
        state.projects.push(created);
        return HttpResponse.json(created, { status: 201 });
      }),
    );
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Create project" }));
    await waitForPreselection();
    await user.type(screen.getByLabelText(/Name/), "Research notes");
    await user.click(screen.getByRole("button", { name: "Create" }));
    expect(await screen.findByText("Research notes")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(posted).toEqual([{ name: "Research notes", team_id: "t-1" }]);
  });

  it("keeps Create disabled while the request is pending", async () => {
    let resolveRequest: (() => void) | undefined;
    server.use(
      http.post("*/projects", async () => {
        await new Promise<void>((resolve) => {
          resolveRequest = resolve;
        });
        return HttpResponse.json(
          { id: "p-new", name: "New", is_public: false, created_at: "2026-10-09T12:00:00Z" },
          { status: 201 },
        );
      }),
    );
    renderDialog();
    const user = userEvent.setup();
    await waitForPreselection();
    await user.type(screen.getByLabelText(/Name/), "Research notes");
    await user.click(screen.getByRole("button", { name: "Create" }));
    expect(screen.getByRole("button", { name: "Create" })).toBeDisabled();
    await vi.waitFor(() => {
      expect(resolveRequest).toBeDefined();
    });
    resolveRequest?.();
    // The dialog-only render keeps a noop onClose, so assert the button
    // re-enables once the request settles.
    await vi.waitFor(() => {
      expect(screen.getByRole("button", { name: "Create" })).toBeEnabled();
    });
  });

  it("shows an inline error when the team is not found (404)", async () => {
    server.use(
      http.post("*/projects", () =>
        HttpResponse.json({ detail: "Team not found" }, { status: 404 }),
      ),
    );
    renderDialog();
    const user = userEvent.setup();
    await waitForPreselection();
    await user.type(screen.getByLabelText(/Name/), "Research notes");
    await user.click(screen.getByRole("button", { name: "Create" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Team not found");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("shows a friendly message on 422", async () => {
    server.use(
      http.post("*/projects", () =>
        HttpResponse.json(
          { detail: [{ loc: ["body", "name"], msg: "field required" }] },
          { status: 422 },
        ),
      ),
    );
    renderDialog();
    const user = userEvent.setup();
    await waitForPreselection();
    await user.type(screen.getByLabelText(/Name/), "Research notes");
    await user.click(screen.getByRole("button", { name: "Create" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Check the highlighted fields and try again.");
    expect(alert).not.toHaveTextContent("field required");
  });

  it("asks for a name when it is blank and does not post", async () => {
    const posts: unknown[] = [];
    server.use(
      http.post("*/projects", ({ request }) => {
        posts.push(request);
        return HttpResponse.json(
          { id: "p-new", name: "New", is_public: false, created_at: "2026-10-09T12:00:00Z" },
          { status: 201 },
        );
      }),
    );
    renderDialog();
    const user = userEvent.setup();
    await waitForPreselection();
    await user.type(screen.getByLabelText(/Name/), "   ");
    await user.click(screen.getByRole("button", { name: "Create" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Give the project a name.");
    expect(posts).toHaveLength(0);
  });

  it("cancel closes without posting", async () => {
    const posts: unknown[] = [];
    server.use(
      http.post("*/projects", ({ request }) => {
        posts.push(request);
        return HttpResponse.json(
          { id: "p-new", name: "New", is_public: false, created_at: "2026-10-09T12:00:00Z" },
          { status: 201 },
        );
      }),
    );
    const onClose = vi.fn();
    renderDialog(onClose);
    const user = userEvent.setup();
    await waitForPreselection();
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(posts).toHaveLength(0);
  });

  it("shows an inline error when the teams fetch fails (404 stale workspace)", async () => {
    server.use(
      http.get("*/workspaces/w-1/teams", () =>
        HttpResponse.json({ detail: "Workspace not found" }, { status: 404 }),
      ),
    );
    renderDialog();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Workspace not found");
    // The team select stays disabled: there is nothing valid to pick.
    expect(screen.getByLabelText(/Team/)).toHaveAttribute("aria-disabled", "true");
  });

  it("shows an inline error when the workspaces fetch fails", async () => {
    server.use(
      http.get("*/workspaces", () =>
        HttpResponse.json({ detail: "Workspaces unavailable" }, { status: 500 }),
      ),
    );
    renderDialog();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Workspaces unavailable");
    expect(screen.getByLabelText(/Workspace/)).toHaveAttribute("aria-disabled", "true");
  });
});
