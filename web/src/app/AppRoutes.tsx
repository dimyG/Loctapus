import { Navigate, Route, Routes } from "react-router";
import AboutPage from "../features/about/AboutPage";
import LandingPage from "../features/landing/LandingPage";
import LoginPage from "../features/auth/LoginPage";
import ProjectPage from "../features/projects/ProjectPage";
import ProjectsPage from "../features/projects/ProjectsPage";
import RegisterPage from "../features/auth/RegisterPage";
import AppShell from "../layouts/AppShell";
import RequireAuth from "./RequireAuth";

/** All app routes; unknown paths fall back to the landing page. */
export default function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/about" element={<AboutPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      {/* The pathless layout route guards and frames every signed-in page. */}
      <Route
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        <Route path="/projects" element={<ProjectsPage />} />
        <Route path="/projects/:projectId" element={<ProjectPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
