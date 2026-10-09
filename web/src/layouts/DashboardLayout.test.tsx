import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { initialRootState } from "../app/store";
import { renderWithProviders } from "../test/test-utils";
import DashboardLayout from "./DashboardLayout";

describe("DashboardLayout", () => {
  it("renders the topbar wordmark and children", () => {
    // The layout is only mounted inside guarded routes, so seed a session.
    renderWithProviders(
      <DashboardLayout>
        <div>dashboard-content</div>
      </DashboardLayout>,
      {
        preloadedState: {
          ...initialRootState(),
          auth: {
            token: "t-1",
            user: { id: "u-1", email: "user@example.test" },
            status: "idle" as const,
          },
        },
      },
    );
    expect(screen.getByText("RAG")).toBeInTheDocument();
    expect(screen.getByText("dashboard-content")).toBeInTheDocument();
  });
});
