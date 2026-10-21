import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { renderWithProviders } from "../test/test-utils";
import AuthFrame from "./AuthFrame";

describe("AuthFrame", () => {
  it("renders the wordmark, the mode switcher, and children inside the outlined card", async () => {
    renderWithProviders(
      <AuthFrame>
        <div>auth-content</div>
      </AuthFrame>,
    );
    expect(screen.getByRole("link", { name: "RAG" })).toHaveAttribute("href", "/");
    // The switcher's trigger answers once useColorScheme settles its mount effect.
    expect(await screen.findByRole("button", { name: "color mode" })).toBeInTheDocument();
    const card = screen.getByText("auth-content").closest(".MuiCard-root");
    expect(card).toBeInTheDocument();
    expect(card).toHaveClass("MuiPaper-outlined");
  });
});
