import { screen } from "@testing-library/react";
import { Route, Routes, useLocation } from "react-router";
import { describe, expect, it } from "vitest";
import { renderWithProviders } from "../../test/test-utils";
import ProjectRedirect from "./ProjectRedirect";

/** Renders the current pathname so the redirect is asserted on the URL itself. */
function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}</div>;
}

describe("ProjectRedirect", () => {
  it("sends a bare project URL to its sources section", () => {
    renderWithProviders(
      <Routes>
        <Route path="/projects/:projectId" element={<ProjectRedirect />} />
        <Route path="*" element={<LocationProbe />} />
      </Routes>,
      { route: "/projects/p-1" },
    );
    expect(screen.getByTestId("location")).toHaveTextContent("/projects/p-1/sources");
  });
});
