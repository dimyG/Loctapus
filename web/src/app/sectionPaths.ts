/** The URL sections the signed-in shell distinguishes. */
export type Section = "projects" | "sources" | "chat";

// /projects plus an id segment: /projects/p-1, /projects/p-1/sources, ...
const projectIdPattern = /^\/projects\/([^/]+)/;

// A section segment under a project, at the end of the path or with more path below it.
const sectionPattern = /^\/projects\/[^/]+\/(sources|chat)(?:\/|$)/;

/** The project id a pathname sits under, or null when there is none. */
export function projectIdFromPath(pathname: string): string | null {
  const match = projectIdPattern.exec(pathname);
  return match === null ? null : match[1];
}

/** The path of one project section: sources or chat under the given project. */
export function sectionPath(section: "sources" | "chat", projectId: string): string {
  return `/projects/${projectId}/${section}`;
}

/**
 * Swaps the `/projects/:id` segment for another project and keeps everything
 * after it, so a swap from deep inside a section stays just as deep - this is
 * what preserves the open page across a project switch. Paths without a
 * project segment pass through unchanged.
 */
export function switchProjectPath(pathname: string, newProjectId: string): string {
  const projectId = projectIdFromPath(pathname);
  if (projectId === null) {
    return pathname;
  }
  const afterProject = pathname.slice(`/projects/${projectId}`.length);
  return `/projects/${newProjectId}${afterProject}`;
}

/**
 * The one section a pathname belongs to: the projects list only on exactly
 * `/projects`, sources and chat under their segment and anything below it.
 * A bare project page belongs to no section.
 */
export function activeSection(pathname: string): Section | null {
  if (pathname === "/projects") {
    return "projects";
  }
  const match = sectionPattern.exec(pathname);
  if (match === null) {
    return null;
  }
  return match[1] as Exclude<Section, "projects">;
}
