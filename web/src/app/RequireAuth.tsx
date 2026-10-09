import type { ReactNode } from "react";
import { Navigate } from "react-router";
import { selectAuthStatus, selectToken } from "../features/auth/authSlice";
import BootSplash from "./BootSplash";
import { useAppSelector } from "./hooks";

/**
 * Route guard: booting sessions see the splash, token-less sessions are sent
 * to login, and authenticated sessions render the guarded content.
 */
export default function RequireAuth({ children }: { children: ReactNode }) {
  const status = useAppSelector(selectAuthStatus);
  const token = useAppSelector(selectToken);
  if (status === "booting") {
    return <BootSplash />;
  }
  if (token === null) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
}
