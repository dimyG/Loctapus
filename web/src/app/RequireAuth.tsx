import type { ReactNode } from "react";
import { Navigate } from "react-router";
import { selectAuthStatus, selectToken } from "../features/auth/authSlice";
import BootSplash from "./BootSplash";
import { useAppSelector } from "./hooks";

/**
 * Route guard: booting sessions and in-flight auth transitions (busy) see
 * the splash, token-less idle sessions are sent to login, and authenticated
 * sessions render the guarded content. The busy case matters during sign-out:
 * the session clears synchronously while the guard is still mounted, and
 * without the splash it would bounce the user to /login instead of letting
 * the sign-out navigation land on the public landing page.
 */
export default function RequireAuth({ children }: { children: ReactNode }) {
  const status = useAppSelector(selectAuthStatus);
  const token = useAppSelector(selectToken);
  if (status === "booting" || status === "busy") {
    return <BootSplash />;
  }
  if (token === null) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
}
