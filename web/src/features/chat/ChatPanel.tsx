import ArrowUpwardRoundedIcon from "@mui/icons-material/ArrowUpwardRounded";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useEffect, useRef, useState } from "react";
import type { JSX, KeyboardEvent } from "react";
import { getErrorMessage } from "../../app/api";
import { gray } from "../../theme/themePrimitives";
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

/** Builds the chip label for a chunk: `[i] filename`, without the heading path. */
function chipLabel(chunk: RetrievedChunk, index: number): string {
  return `[${index + 1}] ${chunk.filename}`;
}

/** The small source chips under an answer; a chip opens a dialog with its chunk. */
function SourcesChips({ chunks }: { chunks: RetrievedChunk[] }) {
  // One dialog open at a time: the state holds the open chip's id.
  const [openId, setOpenId] = useState<string | null>(null);
  const openIndex = chunks.findIndex((chunk) => chunk.id === openId);
  const openChunk = openIndex >= 0 ? chunks[openIndex] : undefined;

  return (
    <>
      <Stack direction="row" spacing={0.5} useFlexGap sx={{ flexWrap: "wrap" }}>
        {chunks.map((chunk, index) => (
          <Chip
            key={chunk.id}
            size="small"
            variant="outlined"
            label={chipLabel(chunk, index)}
            onClick={() => setOpenId(chunk.id)}
          />
        ))}
      </Stack>
      <Dialog open={openChunk !== undefined} onClose={() => setOpenId(null)} maxWidth="sm">
        {openChunk !== undefined && (
          <>
            <DialogTitle>{chunkLabel(openChunk, openIndex)}</DialogTitle>
            <DialogContent>
              <Typography sx={{ whiteSpace: "pre-wrap" }}>{openChunk.text}</Typography>
            </DialogContent>
            <DialogActions>
              <Button onClick={() => setOpenId(null)}>Close</Button>
            </DialogActions>
          </>
        )}
      </Dialog>
    </>
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
    <Box
      sx={{
        mx: "auto",
        width: "100%",
        maxWidth: 760,
        display: "flex",
        flexDirection: "column",
        height: { xs: "calc(100dvh - 176px)", sm: "calc(100dvh - 192px)" },
      }}
    >
      <Box
        sx={{
          flexGrow: 1,
          overflowY: "auto",
          display: "flex",
          flexDirection: "column",
          gap: 2,
        }}
      >
        {turns.map((turn) => (
          <Box key={turn.id} sx={{ display: "flex", flexDirection: "column" }}>
            <Box
              sx={{
                ml: "auto",
                maxWidth: "80%",
                borderRadius: "18px",
                px: 2,
                py: 1,
                backgroundColor: "action.hover",
              }}
            >
              <Typography variant="body2">{turn.question}</Typography>
            </Box>
            {turn.answer !== undefined ? (
              <Box>
                <Typography variant="body1" sx={{ whiteSpace: "pre-wrap" }}>
                  {turn.answer}
                </Typography>
                {turn.chunks !== undefined && turn.chunks.length > 0 && (
                  <SourcesChips chunks={turn.chunks} />
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
              <Stack
                direction="row"
                spacing={1}
                sx={{ alignItems: "center", color: "text.secondary" }}
              >
                <CircularProgress size={16} color="inherit" />
                <Typography>Thinking...</Typography>
              </Stack>
            )}
          </Box>
        ))}
        <div ref={sentinelRef} />
      </Box>
      <Box sx={{ border: "1px solid", borderColor: "divider", borderRadius: 1, p: 1 }}>
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
        <Box sx={{ display: "flex", justifyContent: "flex-end" }}>
          <IconButton
            aria-label="Ask"
            disabled={pending || text.trim() === ""}
            onClick={submit}
            sx={(theme) => ({
              width: 40,
              height: 40,
              borderRadius: "50%",
              backgroundColor: "primary.main",
              color: "primary.contrastText",
              "&:hover": {
                backgroundColor: "primary.dark",
              },
              "&.Mui-disabled": {
                backgroundColor: gray[100],
                color: gray[500],
              },
              ...theme.applyStyles("dark", {
                "&.Mui-disabled": {
                  backgroundColor: gray[800],
                  color: gray[500],
                },
              }),
            })}
          >
            {pending ? <CircularProgress size={16} color="inherit" /> : <ArrowUpwardRoundedIcon />}
          </IconButton>
        </Box>
      </Box>
    </Box>
  );
}
