import { expect, test } from "@playwright/test";

// The marketing pages are anonymous, so these tests need no database seeding.
const MOBILE = { width: 390, height: 844 };
const DESKTOP = { width: 1280, height: 800 };

test.describe("marketing navbar", () => {
  test("mobile keeps the brand and CTA and moves the rest into the menu", async ({ page }) => {
    await page.setViewportSize(MOBILE);
    await page.goto("/");
    const navbar = page.getByRole("banner");
    await expect(navbar.getByRole("link", { name: "Loctapus" })).toBeVisible();
    await expect(navbar.getByRole("link", { name: "Get started" })).toBeVisible();
    await expect(navbar.getByRole("link", { name: "About" })).toBeHidden();
    await expect(navbar.getByRole("link", { name: "Sign in" })).toBeHidden();
    await expect(navbar.getByRole("button", { name: "color mode" })).toBeHidden();
    await expect(navbar.getByRole("button", { name: "menu" })).toBeVisible();

    // A squeezed, wrapped pill would grow taller or overflow the viewport.
    const box = await navbar.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.height).toBeLessThan(80);
    const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    expect(scrollWidth).toBeLessThanOrEqual(MOBILE.width);

    await navbar.getByRole("button", { name: "menu" }).click();
    const menu = page.getByRole("navigation", { name: "Mobile menu" });
    await expect(menu.getByRole("link", { name: "About" })).toBeVisible();
    await expect(menu.getByRole("link", { name: "Sign in" })).toBeVisible();
    await expect(menu.getByRole("button", { name: "color mode" })).toBeVisible();
  });

  test("desktop shows the full navbar and no hamburger", async ({ page }) => {
    await page.setViewportSize(DESKTOP);
    await page.goto("/");
    const navbar = page.getByRole("banner");
    await expect(navbar.getByRole("link", { name: "About" })).toBeVisible();
    await expect(navbar.getByRole("link", { name: "Sign in" })).toBeVisible();
    await expect(navbar.getByRole("link", { name: "Get started" })).toBeVisible();
    await expect(navbar.getByRole("button", { name: "color mode" })).toBeVisible();
    await expect(navbar.getByRole("button", { name: "menu" })).toBeHidden();
  });

  test("an open menu dismisses itself when the viewport crosses to desktop", async ({ page }) => {
    await page.setViewportSize(MOBILE);
    await page.goto("/");
    await page.getByRole("banner").getByRole("button", { name: "menu" }).click();
    await expect(page.getByRole("navigation", { name: "Mobile menu" })).toBeVisible();
    await page.setViewportSize(DESKTOP);
    await expect(page.getByRole("navigation", { name: "Mobile menu" })).toBeHidden();
  });
});
