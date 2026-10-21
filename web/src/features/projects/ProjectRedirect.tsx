import type { JSX } from "react";
import { Navigate, useParams } from "react-router";
import { sectionPath } from "../../app/sectionPaths";

/**
 * The bare project URL's only job: land on the project's sources section,
 * so each project scope keeps exactly one canonical entry URL.
 */
export default function ProjectRedirect(): JSX.Element {
  const { projectId } = useParams<{ projectId: string }>();
  return (
    <Navigate
      to={projectId !== undefined ? sectionPath("sources", projectId) : "/projects"}
      replace
    />
  );
}
