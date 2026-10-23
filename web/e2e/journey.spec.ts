import { execFile } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { promisify } from "node:util";
import { expect, test } from "@playwright/test";
import { PYTHON } from "./venv";

const execFileAsync = promisify(execFile);

const E2E_DB_SCRIPT = "../backend/scripts/e2e_db.py";
const TINY_PDF = "../backend/tests/fixtures/tiny.pdf";

/** Empties the E2E database so each test starts with zero users. */
async function truncateDatabase() {
  await execFileAsync(PYTHON, [E2E_DB_SCRIPT, "truncate"]);
}

/** Writes a fresh sample DOCX via the backend script and returns its temp dir and path. */
async function makeSampleDocx() {
  const dir = await mkdtemp(join(tmpdir(), "rag-e2e-"));
  const docxPath = join(dir, "sample.docx");
  await execFileAsync(PYTHON, ["scripts/make_sample_docx.py", docxPath], { cwd: "../backend" });
  return { dir, docxPath };
}

/**
 * Registers a fresh user through the UI and waits for the sources landing.
 * The /app resolver walks their projects newest-first; nothing is chattable
 * yet, so it lands on the default project's sources page.
 */
async function register(page: import("@playwright/test").Page, email: string) {
  await page.goto("/register");
  await page.getByLabel(/Email/).fill(email);
  await page.getByLabel(/^Password/).fill("password123");
  await page.getByLabel(/Confirm password/).fill("password123");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/projects\/[^/]+\/sources$/);
}

// example.test is a special-use TLD that email-validator rejects; the
// backend's own API tests use example.com.
const E2E_EMAIL = () => `e2e-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`;

test.describe("journey", () => {
  test.beforeEach(async () => {
    await truncateDatabase();
  });

  test("register -> default project -> create -> sign out", async ({ page, request }) => {
    const email = E2E_EMAIL();

    // Register: the resolver lands on the seeded Default project's sources.
    await register(page, email);

    // The permanent sidebar's Projects link opens the projects list; the
    // desktop viewport renders it, so the link is directly clickable.
    await page.getByRole("link", { name: "Projects" }).click();
    await expect(page).toHaveURL(/\/projects$/);
    await expect(page.getByRole("cell", { name: "Default" })).toBeVisible();

    // Create a project through the dialog; the team is preselected.
    await page.getByRole("button", { name: "Create project" }).click();
    await page.getByLabel(/Name/).fill("Research notes");
    await page.getByRole("button", { name: "Create", exact: true }).click();
    await expect(page.getByRole("cell", { name: "Research notes" })).toBeVisible();

    const oldToken = await page.evaluate(() => localStorage.getItem("rag.accessToken"));

    // Sign out from the account menu; the landing page is public. The logout
    // POST runs after the local session drops, so wait for it explicitly
    // before asserting the token was revoked server-side.
    const logoutResponse = page.waitForResponse((r) => r.url().includes("/auth/logout"));
    await page.getByRole("button", { name: /account menu/i }).click();
    await page.getByRole("menuitem", { name: "Sign out" }).click();
    await expect(page).toHaveURL("http://localhost:5173/");
    await expect(page.getByRole("heading", { name: /company's knowledge base/i })).toBeVisible();
    await logoutResponse;

    // The old token was revoked server-side: replaying it must 401.
    const response = await request.get("http://localhost:8001/api/projects", {
      headers: { authorization: `Bearer ${oldToken}` },
    });
    expect(response.status()).toBe(401);

    // Registering the same email again surfaces the friendly 409 copy.
    await page.goto("/register");
    await page.getByLabel(/Email/).fill(email);
    await page.getByLabel(/^Password/).fill("password123");
    await page.getByLabel(/Confirm password/).fill("password123");
    await page.getByRole("button", { name: "Create account" }).click();
    await expect(page.getByText("That email is already registered.")).toBeVisible();
  });

  test("register -> default project -> upload pdf and docx -> ready -> chat", async ({ page }) => {
    const { dir, docxPath } = await makeSampleDocx();
    try {
      const email = E2E_EMAIL();

      // Register, then open the file-upload page through the Add source menu;
      // the other source types stay disabled with "Coming soon" chips.
      await register(page, email);
      await page.getByRole("button", { name: "Add source" }).click();
      await page.getByRole("menuitem", { name: "File upload" }).click();
      await expect(page).toHaveURL(/\/projects\/[^/]+\/sources\/upload$/);
      await expect(page.getByRole("link", { name: "Back to sources" })).toBeVisible();

      // The native input is visually folded into the Upload button and takes
      // a multi-file pick in one change event.
      const input = page.getByLabel("Upload");
      await expect(input).toHaveAttribute("multiple");
      await input.setInputFiles([TINY_PDF, docxPath]);
      // First visit to the upload route transforms its modules on the fly, so
      // the rows can land well past the 5s default on a cold stack - the Ready
      // assertion below carries the same headroom for the pipeline itself.
      await expect(page.getByRole("cell", { name: "tiny.pdf" })).toBeVisible({ timeout: 20_000 });
      await expect(page.getByRole("cell", { name: "sample.docx" })).toBeVisible();

      // The default 5s expect timeout does not cover the full pipeline, so the
      // assertion carries an explicit one inside the 30s test budget.
      await expect(page.getByRole("cell", { name: "Ready" })).toHaveCount(2, { timeout: 20_000 });

      // A same-name re-upload of an indexed file is a 409: the alert carries the
      // server copy and the table keeps exactly its two data rows.
      await input.setInputFiles(TINY_PDF);
      await expect(page.getByRole("alert")).toContainText(
        "A file with this name already exists in this project.",
      );
      // The header's cells are columnheaders, so rows with cells are the data rows.
      await expect(page.getByRole("row").filter({ has: page.getByRole("cell") })).toHaveCount(2);

      // Ask through the browser: the sidebar's Chat link keeps the URL's
      // project, and the stub LLM answers offline, grounded in the
      // retrieval this app wires under the chat page.
      await page.getByRole("link", { name: "Chat" }).click();
      await expect(page).toHaveURL(/\/projects\/[^/]+\/chat$/);
      await page.getByLabel("Ask a question").fill("What is this document about?");
      await page.getByRole("button", { name: "Ask", exact: true }).click();
      await expect(page.getByText(/This is a stub answer grounded/i)).toBeVisible();

      // The cited sources render as small chip buttons labeled "[i] filename";
      // a chip opens a dialog titled with the full label and the chunk text.
      await expect(page.getByRole("button", { name: /tiny\.pdf/ })).toBeVisible();
      await expect(page.getByRole("button", { name: /sample\.docx/ })).toBeVisible();
      await page.getByRole("button", { name: /tiny\.pdf/ }).click();
      const dialog = page.getByRole("dialog");
      await expect(dialog).toContainText(/tiny\.pdf/);
      // tiny.pdf indexes as one fixture chunk, so its text is the dialog body.
      await expect(dialog).toContainText("Stub fixture paragraph.");
      await dialog.getByRole("button", { name: "Close" }).click();
      await expect(dialog).not.toBeVisible();

      // Reload: the persisted conversation hydrates back, so the question and
      // the stub answer render straight from the server, not local state.
      await page.reload();
      await expect(page.getByText("What is this document about?")).toBeVisible();
      await expect(page.getByText(/This is a stub answer grounded/i)).toBeVisible();

      // A follow-up threads into the same conversation: the second answer
      // renders and the thread carries both turns' four bubbles.
      await page.getByLabel("Ask a question").fill("And what else does it cover?");
      await page.getByRole("button", { name: "Ask", exact: true }).click();
      await expect(page.getByText("And what else does it cover?")).toBeVisible();
      await expect(page.getByText(/This is a stub answer grounded/i)).toHaveCount(2);
    } finally {
      await rm(dir, { recursive: true, force: true });
    }
  });
});
