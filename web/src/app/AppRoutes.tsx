import { Navigate, Route, Routes } from "react-router";
import AboutPage from "../features/about/AboutPage";
import LandingPage from "../features/landing/LandingPage";
import LoginPage from "../features/auth/LoginPage";
import ProjectPage from "../features/projects/ProjectPage";
import ProjectsPage from "../features/projects/ProjectsPage";
import RegisterPage from "../features/auth/RegisterPage";
import RequireAuth from "./RequireAuth";

/** All app routes; unknown paths fall back to the landing page. */
export default function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/about" element={<AboutPage />} />
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
      <Route
        path="/projects/:projectId"
        element={
          <RequireAuth>
            <ProjectPage />
          </RequireAuth>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
