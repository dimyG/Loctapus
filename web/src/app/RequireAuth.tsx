import type { ReactNode } from "react";
import { Navigate } from "react-router";
import { selectAuthStatus, selectToken } from "../features/auth/authSlice";
import BootSplash from "./BootSplash";
import { useAppSelector } from "./hooks";

/**
 * Route guard. Booting sessions and in-flight auth transitions (busy) see
 * the splash. A just-signed-out session (signedout) routes to the public
 * landing - the sign-out flow owns the routing, and its target is the same
 * landing page, so this can never bounce a sign-out to /login no matter
 * when React commits the navigation. An idle token-less session means the
 * session expired or never existed: that one re-authenticates at /login.
 */
export default function RequireAuth({ children }: { children: ReactNode }) {
  const status = useAppSelector(selectAuthStatus);
  const token = useAppSelector(selectToken);
  if (status === "booting" || status === "busy") {
    return <BootSplash />;
  }
  if (status === "signedout") {
    return <Navigate to="/" replace />;
  }
  if (token === null) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
}
