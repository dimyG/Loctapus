import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { expect, test } from "@playwright/test";
import { PYTHON } from "./venv";

const execFileAsync = promisify(execFile);

const E2E_DB_SCRIPT = "../backend/scripts/e2e_db.py";

// example.test is a special-use TLD that email-validator rejects; the
// backend's own API tests use example.com.
const E2E_EMAIL = () => `e2e-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`;

test.describe("route enforcement", () => {
  test.beforeEach(async () => {
    await execFileAsync(PYTHON, [E2E_DB_SCRIPT, "truncate"]);
  });

  test("logged-out /projects redirects to /login", async ({ page }) => {
    await page.goto("/projects");
    await expect(page).toHaveURL(/\/login$/);
  });

  test("after login with registered credentials, /projects renders", async ({ page }) => {
    const email = E2E_EMAIL();

    // Register through the UI, then sign out to start the logged-out leg.
    await page.goto("/register");
    await page.getByLabel(/Email/).fill(email);
    await page.getByLabel(/^Password/).fill("password123");
    await page.getByLabel(/Confirm password/).fill("password123");
    await page.getByRole("button", { name: "Create account" }).click();
    await expect(page).toHaveURL(/\/projects$/);
    await page.getByRole("button", { name: /account menu/i }).click();
    await page.getByRole("menuitem", { name: "Sign out" }).click();
    await expect(page).toHaveURL("http://localhost:5173/");

    // After sign-out the protected route redirects to login (spec 8.2).
    await page.goto("/projects");
    await expect(page).toHaveURL(/\/login$/);

    // Log back in with the same credentials; the projects table renders.
    await page.goto("/login");
    await page.getByLabel(/Email/).fill(email);
    await page.getByLabel(/^Password/).fill("password123");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page).toHaveURL(/\/projects$/);
    await expect(page.getByRole("cell", { name: "Default" })).toBeVisible();
  });
});
