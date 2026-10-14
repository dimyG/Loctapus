import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import { initialRootState } from "../../app/store";
import { server } from "../../test/server";
import { renderWithProviders } from "../../test/test-utils";
import UploadCard from "./UploadCard";
import { MAX_UPLOAD_MB } from "./uploadRules";

const authed = () => ({
  ...initialRootState(),
  auth: {
    token: "t-1",
    user: { id: "u-1", email: "user@example.test" },
    status: "idle" as const,
  },
});

/** Renders the card standalone; the mutation only needs the api middleware. */
function renderCard() {
  return renderWithProviders(<UploadCard projectId="p-1" />, { preloadedState: authed() });
}

describe("UploadCard", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("renders the upload control with copy derived from the size limit", () => {
    renderCard();
    expect(screen.getByText("Upload documents")).toBeInTheDocument();
    expect(
      screen.getByText(`Add PDF or DOCX files up to ${MAX_UPLOAD_MB} MB.`, { exact: false }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Upload")).toBeInTheDocument();
  });

  it("shows a client rejection in the alert without posting", async () => {
    const posts: unknown[] = [];
    server.use(
      http.post("*/projects/p-1/uploads", ({ request }) => {
        posts.push(request);
        return HttpResponse.json({}, { status: 201 });
      }),
    );
    renderCard();
    const user = userEvent.setup({ applyAccept: false });
    await user.upload(
      screen.getByLabelText("Upload"),
      new File(["plain text"], "notes.txt", { type: "text/plain" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Only PDF and DOCX files are supported.",
    );
    expect(posts).toHaveLength(0);
  });
});
