import Accordion from "@mui/material/Accordion";
import AccordionDetails from "@mui/material/AccordionDetails";
import AccordionSummary from "@mui/material/AccordionSummary";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useEffect, useRef, useState } from "react";
import type { JSX, KeyboardEvent } from "react";
import { getErrorMessage } from "../../app/api";
import { type RetrievedChunk, useAskQuestionMutation } from "./answersApi";

/** One question/answer exchange in the thread. */
type Turn = {
  id: number;
  question: string;
  answer?: string;
  chunks?: RetrievedChunk[];
  error?: string;
};

/** Builds the summary label for a chunk: `[i] filename > a > b`. */
function chunkLabel(chunk: RetrievedChunk, index: number): string {
  const path = chunk.heading_path.length > 0 ? ` > ${chunk.heading_path.join(" > ")}` : "";
  return `[${index + 1}] ${chunk.filename}${path}`;
}

/** The collapsed "Sources (n)" accordion holding one inner accordion per chunk. */
function SourcesAccordion({ chunks }: { chunks: RetrievedChunk[] }) {
  return (
    <Accordion>
      <AccordionSummary>{`Sources (${chunks.length})`}</AccordionSummary>
      <AccordionDetails>
        {chunks.map((chunk, index) => (
          <Accordion key={chunk.id} disableGutters>
            <AccordionSummary>{chunkLabel(chunk, index)}</AccordionSummary>
            <AccordionDetails sx={{ whiteSpace: "pre-wrap" }}>{chunk.text}</AccordionDetails>
          </Accordion>
        ))}
      </AccordionDetails>
    </Accordion>
  );
}

/** The project chat panel: a local question/answer thread over the answer endpoint. */
export default function ChatPanel({ projectId }: { projectId: string }): JSX.Element {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState("");
  const [pendingId, setPendingId] = useState<number | null>(null);
  const nextId = useRef(0);
  const sentinelRef = useRef<HTMLDivElement>(null);
  const [askQuestion] = useAskQuestionMutation();

  // Auto-scroll the thread to the newest turn whenever it changes.
  useEffect(() => {
    sentinelRef.current?.scrollIntoView();
  }, [turns, pendingId]);

  // Sends one question into an existing turn, filling answer/chunks or error.
  async function send(question: string, turnId: number) {
    setPendingId(turnId);
    // Drop any stale error so a retry shows the pending placeholder instead of the old alert.
    setTurns((prev) =>
      prev.map((turn) => (turn.id === turnId ? { ...turn, error: undefined } : turn)),
    );
    try {
      const result = await askQuestion({ projectId, body: { query: question } }).unwrap();
      setTurns((prev) =>
        prev.map((turn) =>
          turn.id === turnId ? { ...turn, answer: result.answer, chunks: result.chunks } : turn,
        ),
      );
    } catch (e) {
      const message = getErrorMessage(e);
      setTurns((prev) =>
        prev.map((turn) => (turn.id === turnId ? { ...turn, error: message } : turn)),
      );
    } finally {
      setPendingId(null);
    }
  }

  // Appends a new turn from the input and starts the request.
  function submit() {
    if (pendingId !== null || text.trim() === "") {
      return;
    }
    const id = nextId.current + 1;
    nextId.current = id;
    setTurns((prev) => [...prev, { id, question: text }]);
    // The turn owns the question, so the input resets for the next one.
    setText("");
    void send(text, id);
  }

  // Enter submits; Shift+Enter falls through to the native newline.
  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  }

  const pending = pendingId !== null;

  return (
    <Stack spacing={2}>
      {turns.map((turn) => (
        <Box key={turn.id}>
          <Typography variant="body2" sx={{ fontWeight: 600 }}>
            {turn.question}
          </Typography>
          {turn.answer !== undefined ? (
            <Box>
              <Typography sx={{ whiteSpace: "pre-wrap" }}>{turn.answer}</Typography>
              {turn.chunks !== undefined && turn.chunks.length > 0 && (
                <SourcesAccordion chunks={turn.chunks} />
              )}
            </Box>
          ) : turn.error !== undefined ? (
            <Stack spacing={1}>
              <Alert role="alert" severity="error">
                {turn.error}
              </Alert>
              <Button
                variant="outlined"
                disabled={pending}
                onClick={() => void send(turn.question, turn.id)}
              >
                Try again
              </Button>
            </Stack>
          ) : (
            <Typography>Thinking...</Typography>
          )}
        </Box>
      ))}
      <div ref={sentinelRef} />
      <TextField
        label="Ask a question"
        multiline
        minRows={2}
        fullWidth
        disabled={pending}
        value={text}
        onChange={(event) => setText(event.target.value)}
        onKeyDown={handleKeyDown}
      />
      <Button variant="contained" disabled={pending || text.trim() === ""} onClick={submit}>
        Ask
      </Button>
    </Stack>
  );
}
