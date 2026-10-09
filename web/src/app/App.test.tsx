import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import App from "./App";

describe("App shell", () => {
  it("renders the app shell with the RAG wordmark", () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: "RAG" })).toBeInTheDocument();
  });
});
