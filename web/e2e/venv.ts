import { existsSync } from "node:fs";
import { dirname, join } from "node:path";

/**
 * Locates the backend virtualenv's python. `RAG_E2E_PYTHON` wins when set, so
 * checkouts whose venv the walk cannot reach (for example a worktree on
 * another drive) can point at it explicitly. Otherwise the walk looks for
 * `.venv/Scripts/python.exe` upward from `web/`: in a normal checkout the venv
 * sits at the repo root; inside a `.worktrees/<name>` worktree it lives in the
 * main checkout, further up.
 */
export function findVenvPython(): string {
  const override = process.env.RAG_E2E_PYTHON;
  if (override !== undefined && override !== "") {
    if (!existsSync(override)) {
      throw new Error(`RAG_E2E_PYTHON points at a missing file: ${override}`);
    }
    return override;
  }
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
