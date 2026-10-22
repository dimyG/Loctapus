import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { renderWithProviders } from "../test/test-utils";
import BrandMark from "./BrandMark";

describe("BrandMark", () => {
  it("renders the Loctapus wordmark with the decorative logo", () => {
    renderWithProviders(<BrandMark />);
    expect(screen.getByText("Loctapus")).toBeInTheDocument();
    // The empty alt keeps the logo out of the accessibility tree, so an
    // enclosing link reads "Loctapus" from the wordmark text alone.
    const logo = document.querySelector('img[src="/logo.png"]');
    expect(logo).toBeInTheDocument();
    expect(logo).toHaveAttribute("alt", "");
  });
});
