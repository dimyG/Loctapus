import { fireEvent, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router";
import { useLocation } from "react-router";
import { describe, expect, it } from "vitest";
import { initialRootState } from "../app/store";
import { server } from "../test/server";
import { renderWithProviders } from "../test/test-utils";
import ProjectSelect from "./ProjectSelect";

/** Signed-in state; the select renders behind the auth guard in the real app. */
const authed = () => ({
  ...initialRootState(),
  auth: {
    token: "t-1",
    user: { id: "u-1", email: "user@example.test" },
    status: "idle" as const,
  },
});

// Oldest first on purpose: the newest-first ordering must come from the code,
// not from the fixture. p-2 is the latest project.
const projectRows = [
  { id: "p-1", name: "Default", is_public: false, created_at: "2026-10-09T10:00:00Z" },
  { id: "p-2", name: "Research", is_public: true, created_at: "2026-10-10T11:00:00Z" },
];

/** Prints the live pathname, so every navigation lands as observable text. */
function LocationProbe() {
  return <div>at:{useLocation().pathname}</div>;
}

/** Renders the select beside echoing stub routes at the given initial route. */
function renderSelect(route: string, projects: unknown[] = projectRows) {
  server.use(http.get("*/projects", () => HttpResponse.json(projects)));
  return renderWithProviders(
    <>
      <ProjectSelect />
      <Routes>
        <Route path="/projects" element={<LocationProbe />} />
        <Route path="/projects/:projectId/sources" element={<LocationProbe />} />
        <Route path="/projects/:projectId/sources/upload" element={<LocationProbe />} />
        <Route path="/projects/:projectId/chat" element={<LocationProbe />} />
      </Routes>
    </>,
    { route, preloadedState: authed() },
  );
}

/** Opens the select and waits for the options; a resolved list proves the query settled. */
async function openOptions() {
  fireEvent.mouseDown(screen.getByRole("combobox", { name: "Project" }));
  return screen.findAllByRole("option");
}

describe("ProjectSelect", () => {
  it("shows the URL's project", async () => {
    renderSelect("/projects/p-1/sources");
    // While the menu is open, MUI aria-hides the app root so screen readers
    // only see the modal; hold the element reference from before the open.
    const combobox = screen.getByRole("combobox", { name: "Project" });
    await openOptions();
    expect(combobox).toHaveTextContent("Default");
  });

  it("lists projects newest first", async () => {
    renderSelect("/projects/p-1/sources");
    const options = await openOptions();
    expect(options).toHaveLength(2);
    expect(options[0]).toHaveTextContent("Research");
    expect(options[1]).toHaveTextContent("Default");
  });

  it("navigates to the swapped project's sources section", async () => {
    renderSelect("/projects/p-1/sources");
    await openOptions();
    fireEvent.click(screen.getByRole("option", { name: "Research" }));
    expect(await screen.findByText("at:/projects/p-2/sources")).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Project" })).toHaveTextContent("Research");
  });

  it("keeps the deep section when swapping projects", async () => {
    renderSelect("/projects/p-1/sources/upload");
    await openOptions();
    fireEvent.click(screen.getByRole("option", { name: "Research" }));
    expect(await screen.findByText("at:/projects/p-2/sources/upload")).toBeInTheDocument();
  });

  it("shows the placeholder at /projects and picks a project from there", async () => {
    renderSelect("/projects");
    const combobox = screen.getByRole("combobox", { name: "Project" });
    expect(combobox).toHaveTextContent("Select project");
    await openOptions();
    fireEvent.click(screen.getByRole("option", { name: "Research" }));
    expect(await screen.findByText("at:/projects/p-2/sources")).toBeInTheDocument();
  });

  it("is disabled with no projects to choose", async () => {
    renderSelect("/projects", []);
    const combobox = screen.getByRole("combobox", { name: "Project" });
    // The disabled state settles once the empty list resolves.
    await waitFor(() => {
      expect(combobox).toHaveAttribute("aria-disabled", "true");
      expect(combobox).toHaveTextContent("No projects");
    });
  });

  it("shows the placeholder for a stale project id", async () => {
    renderSelect("/projects/p-9/sources", [projectRows[1]]);
    const combobox = screen.getByRole("combobox", { name: "Project" });
    await openOptions();
    expect(combobox).toHaveTextContent("Select project");
  });
});
