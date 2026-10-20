import { api } from "../../app/api";

/** One retrieved chunk as the answer endpoint returns it. */
export type RetrievedChunk = {
  id: string;
  document_id: string;
  source_item_id: string;
  filename: string;
  position: number;
  heading_path: string[];
  chunk_type: string;
  text: string;
  score: number;
};

/** The answer endpoint body: generated text plus its supporting chunks. */
export type Answer = { answer: string; chunks: RetrievedChunk[] };

/** Server state for the chat feature, injected into the base api client. */
export const answersApi = api.injectEndpoints({
  endpoints: (build) => ({
    askQuestion: build.mutation<Answer, { projectId: string; body: { query: string } }>({
      query: ({ projectId, body }) => ({
        url: `/projects/${projectId}/answer`,
        method: "POST",
        body,
      }),
    }),
  }),
});

export const { useAskQuestionMutation } = answersApi;
