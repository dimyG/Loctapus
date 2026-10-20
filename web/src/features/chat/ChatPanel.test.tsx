import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { initialRootState } from "../../app/store";
import { server } from "../../test/server";
import { renderWithProviders } from "../../test/test-utils";
import type { Answer } from "./answersApi";
import ChatPanel from "./ChatPanel";

/** Stable fixture the answer endpoint returns unless a test overrides it. */
const answerFixture: Answer = {
  answer: "Rotate the garage key from the admin UI. [1]",
  chunks: [
    {
      id: "c-1",
      document_id: "d-1",
      source_item_id: "s-1",
      filename: "handbook.pdf",
      position: 0,
      heading_path: ["Keys", "Rotation"],
      chunk_type: "text",
      text: "To rotate the key, open the admin UI and click Rotate.",
      score: 0.75,
    },
  ],
};

const authed = () => ({
  ...initialRootState(),
  auth: {
    token: "t-1",
    user: { id: "u-1", email: "user@example.test" },
    status: "idle" as const,
  },
});

/** Renders the panel with a signed-in session on project p-1. */
function renderPanel() {
  renderWithProviders(<ChatPanel projectId="p-1" />, { preloadedState: authed() });
}

describe("ChatPanel", () => {
  it("asks a question and renders the answer", async () => {
    const posts: { query: string }[] = [];
    server.use(
      http.post("*/api/projects/p-1/answer", async ({ request }) => {
        posts.push((await request.json()) as { query: string });
        return HttpResponse.json(answerFixture);
      }),
    );
    renderPanel();
    const user = userEvent.setup({ applyAccept: false });
    await user.type(screen.getByLabelText("Ask a question"), "How do I rotate the garage key?");
    await user.click(screen.getByRole("button", { name: "Ask" }));
    expect(await screen.findByText(answerFixture.answer)).toBeInTheDocument();
    expect(
      screen.getByText("How do I rotate the garage key?", { selector: "p" }),
    ).toBeInTheDocument();
    expect(posts).toEqual([{ query: "How do I rotate the garage key?" }]);
  });

  it("enter submits and shift-enter inserts a newline", async () => {
    const posts: { query: string }[] = [];
    server.use(
      http.post("*/api/projects/p-1/answer", async ({ request }) => {
        posts.push((await request.json()) as { query: string });
        return HttpResponse.json(answerFixture);
      }),
    );
    renderPanel();
    const textbox = screen.getByLabelText("Ask a question");
    const user = userEvent.setup({ applyAccept: false });
    await user.type(textbox, "first line{Shift>}{Enter}{/Shift}");
    // Shift+Enter is a plain newline, never a submit.
    expect(posts).toHaveLength(0);
    expect(textbox).toHaveValue("first line\n");
    await user.type(textbox, "{Enter}");
    expect(await screen.findByText(answerFixture.answer)).toBeInTheDocument();
    expect(posts).toEqual([{ query: "first line\n" }]);
  });

  it("keeps the input disabled while the request is pending", async () => {
    let resolveAnswer!: (response: Response) => void;
    server.use(
      http.post(
        "*/api/projects/p-1/answer",
        () =>
          new Promise<Response>((resolve) => {
            resolveAnswer = resolve;
          }),
      ),
    );
    renderPanel();
    const textbox = screen.getByLabelText("Ask a question");
    const ask = screen.getByRole("button", { name: "Ask" });
    const user = userEvent.setup({ applyAccept: false });
    await user.type(textbox, "How long does indexing take?");
    await user.click(ask);
    await waitFor(() => expect(ask).toBeDisabled());
    expect(textbox).toBeDisabled();
    resolveAnswer(HttpResponse.json(answerFixture));
    expect(await screen.findByText(answerFixture.answer)).toBeInTheDocument();
    await waitFor(() => expect(ask).toBeEnabled());
    await waitFor(() => expect(textbox).toBeEnabled());
  });

  it("lists and expands the answer sources", async () => {
    server.use(http.post("*/api/projects/p-1/answer", () => HttpResponse.json(answerFixture)));
    renderPanel();
    const user = userEvent.setup({ applyAccept: false });
    await user.type(screen.getByLabelText("Ask a question"), "Where are keys rotated?");
    await user.click(screen.getByRole("button", { name: "Ask" }));
    await screen.findByText(answerFixture.answer);
    await user.click(screen.getByText("Sources (1)"));
    const row = await screen.findByText("[1] handbook.pdf > Keys > Rotation");
    await user.click(row);
    expect(
      screen.getByText("To rotate the key, open the admin UI and click Rotate."),
    ).toBeInTheDocument();
  });

  it("shows an error card and try again re-sends", async () => {
    let calls = 0;
    let resolveRetry!: (response: Response) => void;
    server.use(
      http.post("*/api/projects/p-1/answer", () => {
        calls += 1;
        if (calls === 1) {
          return HttpResponse.json({ detail: "boom" }, { status: 500 });
        }
        // The retry hangs until the test resolves it, to observe the in-flight state.
        return new Promise<Response>((resolve) => {
          resolveRetry = resolve;
        });
      }),
    );
    renderPanel();
    const user = userEvent.setup({ applyAccept: false });
    await user.type(screen.getByLabelText("Ask a question"), "Rotate the garage key?");
    await user.click(screen.getByRole("button", { name: "Ask" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("boom");
    await user.click(screen.getByRole("button", { name: "Try again" }));
    // While the retry is in flight the placeholder shows and the stale alert is gone.
    expect(await screen.findByText("Thinking...")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    await waitFor(() => expect(calls).toBe(2));
    resolveRetry(HttpResponse.json(answerFixture));
    expect(await screen.findByText(answerFixture.answer)).toBeInTheDocument();
    expect(calls).toBe(2);
  });
});
