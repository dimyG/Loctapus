import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Link from "@mui/material/Link";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import type { FormEvent } from "react";
import { useState } from "react";
import { Link as RouterLink, Navigate } from "react-router";
import { getErrorMessage } from "../../app/api";
import { useAppDispatch, useAppSelector } from "../../app/hooks";
import AuthLayout from "../../layouts/AuthLayout";
import { registerUser, selectUser } from "./authSlice";

const REQUIRED_COPY = "All fields are required.";
const MISMATCH_COPY = "Passwords do not match.";
const CONFLICT_COPY = "That email is already registered.";

/** Maps errors to form copy, overriding 409 with the fixed conflict message. */
function toFormMessage(error: unknown): string {
  if (typeof error === "object" && error !== null && "status" in error) {
    if ((error as { status?: number | string }).status === 409) {
      return CONFLICT_COPY;
    }
  }
  return getErrorMessage(error);
}

/** The registration page. */
export default function RegisterPage() {
  const dispatch = useAppDispatch();
  const user = useAppSelector(selectUser);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showSignIn, setShowSignIn] = useState(false);

  if (user !== null) {
    return <Navigate to="/projects" replace />;
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    // Client-side checks run before anything reaches the API.
    if (email === "" || password === "" || confirm === "") {
      setError(REQUIRED_COPY);
      setShowSignIn(false);
      return;
    }
    // The API enforces 8 characters too (422); catching it here keeps the
    // hint visible instead of the generic validation copy.
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      setShowSignIn(false);
      return;
    }
    if (password !== confirm) {
      setError(MISMATCH_COPY);
      setShowSignIn(false);
      return;
    }
    setPending(true);
    setError(null);
    setShowSignIn(false);
    try {
      await dispatch(registerUser({ email, password })).unwrap();
    } catch (e) {
      setError(toFormMessage(e));
      setShowSignIn(toFormMessage(e) === CONFLICT_COPY);
    } finally {
      setPending(false);
    }
  }

  return (
    <AuthLayout>
      <Typography component="h1" variant="h5" sx={{ fontWeight: 600 }}>
        Create account
      </Typography>
      <Box component="form" onSubmit={handleSubmit} noValidate sx={{ mt: 2 }}>
        <Stack spacing={2}>
          {error !== null && (
            <Alert role="alert" severity="error">
              {error}{" "}
              {showSignIn && (
                <Link component={RouterLink} to="/login">
                  Sign in
                </Link>
              )}
            </Alert>
          )}
          <TextField
            label="Email"
            type="email"
            name="email"
            autoComplete="email"
            required
            fullWidth
            disabled={pending}
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
          <TextField
            label="Password"
            type="password"
            name="password"
            autoComplete="new-password"
            required
            fullWidth
            disabled={pending}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
          <TextField
            label="Confirm password"
            type="password"
            name="confirm"
            autoComplete="new-password"
            required
            fullWidth
            disabled={pending}
            value={confirm}
            onChange={(event) => setConfirm(event.target.value)}
          />
          <Button type="submit" variant="contained" disabled={pending} fullWidth>
            Create account
          </Button>
          <Typography variant="body2" sx={{ textAlign: "center" }}>
            Already have an account?{" "}
            <Link component={RouterLink} to="/login">
              Sign in
            </Link>
          </Typography>
        </Stack>
      </Box>
    </AuthLayout>
  );
}
