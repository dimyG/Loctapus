import { Navigate, Route, Routes } from "react-router";
import LandingPage from "../features/landing/LandingPage";
import LoginPage from "../features/auth/LoginPage";
import ProjectsPage from "../features/projects/ProjectsPage";
import RegisterPage from "../features/auth/RegisterPage";
import RequireAuth from "./RequireAuth";

/** All app routes; unknown paths fall back to the landing page. */
export default function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route
        path="/projects"
        element={
          <RequireAuth>
            <ProjectsPage />
          </RequireAuth>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
