import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import Link from "@mui/material/Link";
import type { FormEvent } from "react";
import { useState } from "react";
import { Link as RouterLink, Navigate } from "react-router";
import { getErrorMessage } from "../../app/api";
import { useAppDispatch, useAppSelector } from "../../app/hooks";
import AuthLayout from "../../layouts/AuthLayout";
import { loginUser, selectUser } from "./authSlice";

/** The 401 body is backend detail; the product copy is fixed. */
const INVALID_CREDENTIALS = "Invalid email or password.";

/** Maps errors to form copy, overriding 401 with the fixed message. */
function toFormMessage(error: unknown): string {
  if (typeof error === "object" && error !== null && "status" in error) {
    if ((error as { status?: number | string }).status === 401) {
      return INVALID_CREDENTIALS;
    }
  }
  return getErrorMessage(error);
}

/** The sign-in page. */
export default function LoginPage() {
  const dispatch = useAppDispatch();
  const user = useAppSelector(selectUser);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (user !== null) {
    return <Navigate to="/projects" replace />;
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (email === "" || password === "") {
      setError("All fields are required.");
      return;
    }
    setPending(true);
    setError(null);
    try {
      await dispatch(loginUser({ email, password })).unwrap();
    } catch (e) {
      setError(toFormMessage(e));
    } finally {
      setPending(false);
    }
  }

  return (
    <AuthLayout>
      <Typography component="h1" variant="h5" sx={{ fontWeight: 600 }}>
        Sign in
      </Typography>
      <Box component="form" onSubmit={handleSubmit} noValidate sx={{ mt: 2 }}>
        <Stack spacing={2}>
          {error !== null && (
            <Alert role="alert" severity="error">
              {error}
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
            autoComplete="current-password"
            required
            fullWidth
            disabled={pending}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
          <Button type="submit" variant="contained" disabled={pending} fullWidth>
            Sign in
          </Button>
          <Typography variant="body2" sx={{ textAlign: "center" }}>
            Need an account?{" "}
            <Link component={RouterLink} to="/register">
              Create one
            </Link>
          </Typography>
        </Stack>
      </Box>
    </AuthLayout>
  );
}
