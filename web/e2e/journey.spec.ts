import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { expect, test } from "@playwright/test";
import { PYTHON } from "./venv";

const execFileAsync = promisify(execFile);

const E2E_DB_SCRIPT = "../backend/scripts/e2e_db.py";

/** Empties the E2E database so each test starts with zero users. */
async function truncateDatabase() {
  await execFileAsync(PYTHON, [E2E_DB_SCRIPT, "truncate"]);
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

    // Sign out from the account menu; the landing page is public.
    await page.getByRole("button", { name: /account menu/i }).click();
    await page.getByRole("menuitem", { name: "Sign out" }).click();
    await expect(page).toHaveURL("http://localhost:5173/");
    await expect(page.getByRole("heading", { name: /searchable by meaning/i })).toBeVisible();

    // The old token was revoked server-side: replaying it must 401.
    const response = await request.get("http://localhost:8001/projects", {
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
});
