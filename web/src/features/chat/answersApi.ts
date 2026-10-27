import { api } from "../../app/api";

/** One persisted evidence snapshot as the conversation endpoints return it. */
export type SnapshotChunk = {
  chunk_id: string | null;
  filename: string;
  heading_path: string[];
  text: string;
  document_content_hash: string;
};

/** One conversation message as the latest endpoint returns it. */
export type ConversationMessage = {
  role: "user" | "assistant";
  content: string;
  route: "direct" | "reuse" | "retrieve" | null;
  chunks: SnapshotChunk[];
};

/** The answer endpoint body: generated text plus its persisted snapshots. */
export type Answer = {
  answer: string;
  route: "direct" | "reuse" | "retrieve";
  conversation_id: string;
  chunks: SnapshotChunk[];
};

/** The 201 body of POST /conversations. */
export type ConversationCreated = { conversation_id: string };

/** The latest endpoint body: the caller's newest conversation, hydrated. */
export type LatestConversation = {
  conversation_id: string;
  messages: ConversationMessage[];
};

/** Server state for the chat feature, injected into the base api client. */
export const answersApi = api.injectEndpoints({
  endpoints: (build) => ({
    askQuestion: build.mutation<
      Answer,
      { projectId: string; body: { query: string; conversation_id: string | null } }
    >({
      query: ({ projectId, body }) => ({
        url: `/projects/${projectId}/answer`,
        method: "POST",
        body,
      }),
      invalidatesTags: ["Conversation"],
    }),
    getLatestConversation: build.query<LatestConversation, { projectId: string }>({
      query: ({ projectId }) => `/projects/${projectId}/conversations/latest`,
      providesTags: ["Conversation"],
    }),
    createConversation: build.mutation<ConversationCreated, { projectId: string }>({
      query: ({ projectId }) => ({
        url: `/projects/${projectId}/conversations`,
        method: "POST",
      }),
      invalidatesTags: ["Conversation"],
    }),
  }),
});

export const {
  useAskQuestionMutation,
  useCreateConversationMutation,
  useGetLatestConversationQuery,
} = answersApi;
