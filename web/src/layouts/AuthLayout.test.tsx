import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { renderWithProviders } from "../test/test-utils";
import AuthLayout from "./AuthLayout";

describe("AuthLayout", () => {
  it("renders the wordmark linked home and the content card", () => {
    renderWithProviders(
      <AuthLayout>
        <div>auth-content</div>
      </AuthLayout>,
    );
    expect(screen.getByRole("link", { name: "RAG" })).toHaveAttribute("href", "/");
    expect(screen.getByText("auth-content")).toBeInTheDocument();
  });
});
