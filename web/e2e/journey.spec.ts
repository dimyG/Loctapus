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

/** Registers a fresh user through the UI and waits for /projects. */
async function register(page: import("@playwright/test").Page, email: string) {
  await page.goto("/register");
  await page.getByLabel(/Email/).fill(email);
  await page.getByLabel(/^Password/).fill("password123");
  await page.getByLabel(/Confirm password/).fill("password123");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/projects$/);
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

    // Register: the seeded Default project is visible immediately.
    await register(page, email);
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
    await expect(page.getByRole("heading", { name: /searchable by meaning/i })).toBeVisible();
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

  test("register -> default project -> upload pdf and docx -> ready", async ({ page }) => {
    const { dir, docxPath } = await makeSampleDocx();
    try {
      const email = E2E_EMAIL();

      // Register, then open the seeded Default project through its row link.
      await register(page, email);
      await page.getByRole("cell", { name: "Default" }).getByRole("link").click();
      await expect(page).toHaveURL(/\/projects\/[^/]+$/);

      // The native input is visually folded into the Upload button; setInputFiles
      // fires its change event, which runs the client checks and the upload.
      await page.getByLabel("Upload").setInputFiles(TINY_PDF);
      await expect(page.getByRole("cell", { name: "tiny.pdf" })).toBeVisible();
      await page.getByLabel("Upload").setInputFiles(docxPath);

      // The first upload turning ready flips the page's default to Ask, which
      // hides the cells the assertions below wait on, so the Documents tab is
      // pinned back. MUI fires a Tab's onChange only when it is not already
      // selected, so the pin must wait for the flip: Ask becomes enabled the
      // moment the first upload is ready.
      await expect(page.getByRole("tab", { name: "Ask" })).toBeEnabled({ timeout: 20_000 });
      await page.getByRole("tab", { name: "Documents" }).click();

      // The default 5s expect timeout does not cover the full pipeline, so the
      // assertion carries an explicit one inside the 30s test budget.
      await expect(page.getByRole("cell", { name: "Ready" })).toHaveCount(2, { timeout: 20_000 });

      // A same-name re-upload of an indexed file is a 409: the alert carries the
      // server copy and the table keeps exactly its two data rows.
      await page.getByLabel("Upload").setInputFiles(TINY_PDF);
      await expect(page.getByRole("alert")).toContainText(
        "A file with this name already exists in this project.",
      );
      // The header's cells are columnheaders, so rows with cells are the data rows.
      await expect(page.getByRole("row").filter({ has: page.getByRole("cell") })).toHaveCount(2);

      // Ask through the browser: the stub LLM answers offline, grounded in the
      // retrieval this slice wires under the chat panel.
      await page.getByRole("tab", { name: "Ask" }).click();
      await page.getByLabel("Ask a question").fill("What is this document about?");
      await page.getByRole("button", { name: "Ask", exact: true }).click();
      await expect(page.getByText(/This is a stub answer grounded/i)).toBeVisible();

      // MUI renders AccordionSummary as a native button, so the sources and
      // their rows match as buttons; the row-button selector avoids a strict-mode
      // double match with the hidden Documents panel's table cells.
      await page.getByRole("button", { name: /Sources \(\d+\)/ }).click();
      await expect(page.getByRole("button", { name: /tiny\.pdf/ })).toBeVisible();
      await expect(page.getByRole("button", { name: /sample\.docx/ })).toBeVisible();
    } finally {
      await rm(dir, { recursive: true, force: true });
    }
  });
});
