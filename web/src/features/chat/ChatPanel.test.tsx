import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { initialRootState } from "../../app/store";
import { server } from "../../test/server";
import { renderWithProviders } from "../../test/test-utils";
import type {
  Answer,
  ConversationMessage,
  LatestConversation,
  SnapshotChunk,
} from "./answersApi";
import ChatPanel from "./ChatPanel";

/** Builds one persisted snapshot fixture; tests override only what they assert. */
function snapshot(overrides: Partial<SnapshotChunk> = {}): SnapshotChunk {
  return {
    chunk_id: "c-1",
    filename: "handbook.pdf",
    heading_path: ["Keys", "Rotation"],
    text: "To rotate the key, open the admin UI and click Rotate.",
    document_content_hash: "hash-1",
    ...overrides,
  };
}

/** Stable fixture the answer endpoint returns unless a test overrides it. */
const answerFixture: Answer = {
  answer: "Rotate the garage key from the admin UI. [1]",
  route: "retrieve",
  conversation_id: "conv-9",
  chunks: [snapshot()],
};

/** One hydrated prior turn, as the latest endpoint serves it. */
const latestMessages: ConversationMessage[] = [
  { role: "user", content: "Where are keys rotated?", route: null, chunks: [] },
  {
    role: "assistant",
    content: "Keys rotate in the admin UI. [1]",
    route: "retrieve",
    chunks: [snapshot()],
  },
];

/** Stable fixture for the latest endpoint; tests override per case. */
const latestFixture: LatestConversation = {
  conversation_id: "conv-1",
  messages: latestMessages,
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
    const posts: { query: string; conversation_id: string | null }[] = [];
    server.use(
      http.post("*/api/projects/p-1/answer", async ({ request }) => {
        posts.push(
          (await request.json()) as { query: string; conversation_id: string | null },
        );
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
    // No conversation exists yet (the baseline latest handler 404s), so the ask
    // carries a null id and adopts the served one.
    expect(posts).toEqual([{ query: "How do I rotate the garage key?", conversation_id: null }]);
    // The turn owns the question, so the input resets once it is sent.
    expect(screen.getByLabelText("Ask a question")).toHaveValue("");
  });

  it("enter submits and shift-enter inserts a newline", async () => {
    const posts: { query: string; conversation_id: string | null }[] = [];
    server.use(
      http.post("*/api/projects/p-1/answer", async ({ request }) => {
        posts.push(
          (await request.json()) as { query: string; conversation_id: string | null },
        );
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
    expect(posts).toEqual([{ query: "first line\n", conversation_id: null }]);
  });

  it("keeps Ask disabled for empty and whitespace-only input", async () => {
    renderPanel();
    const user = userEvent.setup({ applyAccept: false });
    const ask = screen.getByRole("button", { name: "Ask" });
    expect(ask).toBeDisabled();
    await user.type(screen.getByLabelText("Ask a question"), "   ");
    expect(ask).toBeDisabled();
  });

  it("shows the sending state", async () => {
    // The answer endpoint never resolves, so the pending state stays observable.
    server.use(http.post("*/api/projects/p-1/answer", () => new Promise<Response>(() => {})));
    renderPanel();
    const user = userEvent.setup({ applyAccept: false });
    const textbox = screen.getByLabelText("Ask a question");
    await user.type(textbox, "How long does indexing take?");
    await user.click(screen.getByRole("button", { name: "Ask" }));
    const ask = screen.getByRole("button", { name: "Ask" });
    await waitFor(() => expect(ask).toBeDisabled());
    expect(within(ask).getByRole("progressbar")).toBeInTheDocument();
    expect(textbox).toBeDisabled();
  });

  it("renders no source chips for a canned empty answer", async () => {
    server.use(
      http.post("*/api/projects/p-1/answer", () =>
        HttpResponse.json({
          answer: "No indexed content in this project matches your question yet.",
          route: "retrieve",
          conversation_id: "conv-1",
          chunks: [],
        }),
      ),
    );
    renderPanel();
    const user = userEvent.setup({ applyAccept: false });
    await user.type(screen.getByLabelText("Ask a question"), "What is this document about?");
    await user.click(screen.getByRole("button", { name: "Ask" }));
    expect(
      await screen.findByText("No indexed content in this project matches your question yet."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/^\[\d+\]/)).not.toBeInTheDocument();
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
    await waitFor(() => expect(textbox).toBeEnabled());
    // The input resets after submit, so Ask stays disabled until it has text.
    expect(ask).toBeDisabled();
    expect(textbox).toHaveValue("");
    await user.type(textbox, "next question");
    await waitFor(() => expect(ask).toBeEnabled());
  });

  it("shows the sources as small chips that open the chunk", async () => {
    server.use(http.post("*/api/projects/p-1/answer", () => HttpResponse.json(answerFixture)));
    renderPanel();
    const user = userEvent.setup({ applyAccept: false });
    await user.type(screen.getByLabelText("Ask a question"), "Where are keys rotated?");
    await user.click(screen.getByRole("button", { name: "Ask" }));
    await screen.findByText(answerFixture.answer);
    // The accordion is gone; the sources are a row of small chips.
    expect(screen.queryByText(/Sources \(\d+\)/)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "[1] handbook.pdf" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("[1] handbook.pdf > Keys > Rotation")).toBeInTheDocument();
    expect(
      within(dialog).getByText("To rotate the key, open the admin UI and click Rotate."),
    ).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Close" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(screen.getByText(answerFixture.answer)).toBeInTheDocument();
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

  it("hydrates the latest conversation and its source chips", async () => {
    server.use(
      http.get("*/api/projects/p-1/conversations/latest", () =>
        HttpResponse.json(latestFixture),
      ),
    );
    renderPanel();
    expect(await screen.findByText("Where are keys rotated?")).toBeInTheDocument();
    expect(screen.getByText("Keys rotate in the admin UI. [1]")).toBeInTheDocument();
    const user = userEvent.setup({ applyAccept: false });
    await user.click(screen.getByRole("button", { name: "[1] handbook.pdf" }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText("[1] handbook.pdf > Keys > Rotation")).toBeInTheDocument();
    expect(
      within(dialog).getByText("To rotate the key, open the admin UI and click Rotate."),
    ).toBeInTheDocument();
  });

  it("starts an empty thread when no conversation exists yet", async () => {
    server.use(
      http.get("*/api/projects/p-1/conversations/latest", () =>
        HttpResponse.json({ detail: "no conversation yet" }, { status: 404 }),
      ),
    );
    renderPanel();
    expect(await screen.findByLabelText("Ask a question")).toBeEnabled();
    expect(screen.queryByText("Where are keys rotated?")).not.toBeInTheDocument();
    expect(screen.queryByText("Keys rotate in the admin UI. [1]")).not.toBeInTheDocument();
  });

  it("threads the hydrated conversation id and adopts the served one", async () => {
    const posts: { query: string; conversation_id: string | null }[] = [];
    // A stateful fake: each answer appends its turn to the hydrated thread, exactly
    // as the persisted backend would serve it back on the invalidated refetch.
    let latest = latestFixture;
    server.use(
      http.get("*/api/projects/p-1/conversations/latest", () => HttpResponse.json(latest)),
      http.post("*/api/projects/p-1/answer", async ({ request }) => {
        const body = (await request.json()) as { query: string; conversation_id: string | null };
        posts.push(body);
        latest = {
          conversation_id: answerFixture.conversation_id,
          messages: [
            ...latest.messages,
            { role: "user", content: body.query, route: null, chunks: [] },
            {
              role: "assistant",
              content: answerFixture.answer,
              route: answerFixture.route,
              chunks: answerFixture.chunks,
            },
          ],
        };
        return HttpResponse.json(answerFixture);
      }),
    );
    renderPanel();
    await screen.findByText("Where are keys rotated?");
    const user = userEvent.setup({ applyAccept: false });
    await user.type(screen.getByLabelText("Ask a question"), "What about the spare key?");
    await user.click(screen.getByRole("button", { name: "Ask" }));
    expect(await screen.findByText(answerFixture.answer)).toBeInTheDocument();
    // The ask carried the hydrated conversation id.
    expect(posts).toEqual([
      { query: "What about the spare key?", conversation_id: "conv-1" },
    ]);
    await user.type(screen.getByLabelText("Ask a question"), "And the master key?");
    await user.click(screen.getByRole("button", { name: "Ask" }));
    expect(
      await screen.findByText("And the master key?", { selector: "p" }),
    ).toBeInTheDocument();
    // The second ask carried the id the first response served.
    expect(posts).toEqual([
      { query: "What about the spare key?", conversation_id: "conv-1" },
      { query: "And the master key?", conversation_id: "conv-9" },
    ]);
  });

  it("starts a new empty conversation from the New chat button", async () => {
    const posts: { query: string; conversation_id: string | null }[] = [];
    let latest: LatestConversation = latestFixture;
    server.use(
      http.get("*/api/projects/p-1/conversations/latest", () => HttpResponse.json(latest)),
      http.post("*/api/projects/p-1/conversations", () => {
        latest = { conversation_id: "conv-2", messages: [] };
        return HttpResponse.json({ conversation_id: "conv-2" }, { status: 201 });
      }),
      http.post("*/api/projects/p-1/answer", async ({ request }) => {
        const body = (await request.json()) as { query: string; conversation_id: string | null };
        posts.push(body);
        // The persisted backend would serve the new turn back on the invalidated
        // latest refetch, so the fake appends it the same way.
        latest = {
          conversation_id: "conv-2",
          messages: [
            ...latest.messages,
            { role: "user", content: body.query, route: null, chunks: [] },
            {
              role: "assistant",
              content: answerFixture.answer,
              route: answerFixture.route,
              chunks: answerFixture.chunks,
            },
          ],
        };
        return HttpResponse.json({ ...answerFixture, conversation_id: "conv-2" });
      }),
    );
    renderPanel();
    expect(await screen.findByText("Where are keys rotated?")).toBeInTheDocument();
    const user = userEvent.setup({ applyAccept: false });
    await user.click(screen.getByRole("button", { name: "New chat" }));
    // The hydrated thread clears once the fresh conversation hydrates.
    await waitFor(() =>
      expect(screen.queryByText("Where are keys rotated?")).not.toBeInTheDocument(),
    );
    await user.type(screen.getByLabelText("Ask a question"), "Fresh question?");
    await user.click(screen.getByRole("button", { name: "Ask" }));
    expect(await screen.findByText(answerFixture.answer)).toBeInTheDocument();
    // The new conversation's id threaded into the fresh ask.
    expect(posts).toEqual([{ query: "Fresh question?", conversation_id: "conv-2" }]);
  });

  it("renders chips for snapshots without chunk ids and duplicate filenames", async () => {
    const twinAnswer: Answer = {
      answer: "Both passages agree. [1] [2]",
      route: "reuse",
      conversation_id: "conv-1",
      chunks: [
        snapshot({ chunk_id: null, filename: "dup.pdf", heading_path: [], text: "first passage" }),
        snapshot({ chunk_id: null, filename: "dup.pdf", heading_path: [], text: "second passage" }),
      ],
    };
    server.use(
      http.post("*/api/projects/p-1/answer", () => HttpResponse.json(twinAnswer)),
    );
    renderPanel();
    const user = userEvent.setup({ applyAccept: false });
    await user.type(screen.getByLabelText("Ask a question"), "duplicate keys?");
    await user.click(screen.getByRole("button", { name: "Ask" }));
    expect(await screen.findByText(twinAnswer.answer)).toBeInTheDocument();
    // Both null-id chips render (React keys fall back to the index) and open their text.
    await user.click(screen.getByRole("button", { name: "[1] dup.pdf" }));
    expect(await within(screen.getByRole("dialog")).findByText("first passage")).toBeInTheDocument();
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Close" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "[2] dup.pdf" }));
    expect(
      await within(screen.getByRole("dialog")).findByText("second passage"),
    ).toBeInTheDocument();
  });
});
