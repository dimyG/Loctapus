import { describe, expect, it } from "vitest";
import { activeSection, projectIdFromPath, sectionPath, switchProjectPath } from "./sectionPaths";

describe("projectIdFromPath", () => {
  it("extracts the id from the section paths", () => {
    expect(projectIdFromPath("/projects/p-1/sources")).toBe("p-1");
    expect(projectIdFromPath("/projects/p-1/sources/upload")).toBe("p-1");
    expect(projectIdFromPath("/projects/p-1/chat")).toBe("p-1");
  });

  it("extracts the id from the bare project page", () => {
    expect(projectIdFromPath("/projects/p-1")).toBe("p-1");
  });

  it("returns null when the URL carries no project", () => {
    expect(projectIdFromPath("/projects")).toBeNull();
    expect(projectIdFromPath("/")).toBeNull();
  });
});

describe("sectionPath", () => {
  it("builds the sources and chat paths for a project", () => {
    expect(sectionPath("sources", "p-1")).toBe("/projects/p-1/sources");
    expect(sectionPath("chat", "p-1")).toBe("/projects/p-1/chat");
  });
});

describe("switchProjectPath", () => {
  it("keeps the deep section when swapping projects", () => {
    expect(switchProjectPath("/projects/p-1/sources/upload", "p-2")).toBe(
      "/projects/p-2/sources/upload",
    );
  });

  it("swaps the project on a shallow section path", () => {
    expect(switchProjectPath("/projects/p-1/sources", "p-2")).toBe("/projects/p-2/sources");
  });

  it("leaves project-less paths untouched", () => {
    expect(switchProjectPath("/projects", "p-2")).toBe("/projects");
  });
});

describe("activeSection", () => {
  it("marks the projects list active only on /projects", () => {
    expect(activeSection("/projects")).toBe("projects");
  });

  it("marks sources active on the sources section and below", () => {
    expect(activeSection("/projects/p-1/sources")).toBe("sources");
    expect(activeSection("/projects/p-1/sources/upload")).toBe("sources");
  });

  it("marks chat active on the chat section", () => {
    expect(activeSection("/projects/p-1/chat")).toBe("chat");
  });

  it("resolves every URL to at most one section", () => {
    const cases: Array<[string, "projects" | "sources" | "chat" | null]> = [
      ["/projects", "projects"],
      ["/projects/p-1/sources", "sources"],
      ["/projects/p-1/sources/upload", "sources"],
      ["/projects/p-1/chat", "chat"],
      ["/projects/p-1", null],
    ];
    for (const [path, expected] of cases) {
      expect(activeSection(path)).toBe(expected);
    }
  });
});
