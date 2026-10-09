import { existsSync } from "node:fs";
import { dirname, join } from "node:path";

/**
 * Locates the backend virtualenv's python by walking up from `web/`. In a
 * normal checkout the venv sits at the repo root; inside a `.worktrees/<name>`
 * worktree it lives in the main checkout, further up.
 */
export function findVenvPython(): string {
  let dir = process.cwd();
  for (let depth = 0; depth < 5; depth += 1) {
    const candidate = join(dir, ".venv", "Scripts", "python.exe");
    if (existsSync(candidate)) {
      return candidate;
    }
    const parent = dirname(dir);
    if (parent === dir) {
      break;
    }
    dir = parent;
  }
  throw new Error("Could not locate .venv/Scripts/python.exe (the backend virtualenv).");
}

export const PYTHON = findVenvPython();
