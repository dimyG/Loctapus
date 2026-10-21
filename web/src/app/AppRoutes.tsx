import { Navigate, Route, Routes } from "react-router";
import AboutPage from "../features/about/AboutPage";
import LandingPage from "../features/landing/LandingPage";
import LoginPage from "../features/auth/LoginPage";
import ProjectRedirect from "../features/projects/ProjectRedirect";
import ProjectsPage from "../features/projects/ProjectsPage";
import RegisterPage from "../features/auth/RegisterPage";
import ChatLanding from "../features/chat/ChatLanding";
import ChatPage from "../features/chat/ChatPage";
import FileUploadPage from "../features/sources/FileUploadPage";
import SourcesPage from "../features/sources/SourcesPage";
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
        <Route path="/app" element={<ChatLanding />} />
        <Route path="/projects" element={<ProjectsPage />} />
        <Route path="/projects/:projectId" element={<ProjectRedirect />} />
        <Route path="/projects/:projectId/sources" element={<SourcesPage />} />
        <Route path="/projects/:projectId/sources/upload" element={<FileUploadPage />} />
        <Route path="/projects/:projectId/chat" element={<ChatPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
