// A. Who can see which page.

import { expect, test } from "@playwright/test";

import { createAccount, signIn } from "./helpers";

test.describe("A. Access and routing", () => {
  for (const path of ["/", "/chat", "/memory", "/profile", "/onboarding", "/no-such-page"]) {
    test(`A1 a logged-out visitor opening ${path} lands on login`, async ({ page }) => {
      await page.goto(path);
      await expect(page).toHaveURL(/\/login$/);
      await expect(page.getByRole("button", { name: "Log in" })).toBeVisible();
    });
  }

  for (const path of ["/login", "/signup"]) {
    test(`A2 a logged-in user opening ${path} is sent to chat`, async ({ page, request }) => {
      await signIn(page, await createAccount(request));
      await page.goto(path);
      await expect(page).toHaveURL(/\/chat\//);
    });
  }

  for (const path of ["/chat", "/memory", "/profile"]) {
    test(`A3 a user who has not onboarded opening ${path} is sent to onboarding`, async ({ page, request }) => {
      await signIn(page, await createAccount(request, { onboarded: false }));
      await page.goto(path);
      await expect(page).toHaveURL(/\/onboarding$/);
      await expect(page.getByRole("heading", { name: "Your birth details" })).toBeVisible();
    });
  }

  test("A4 an onboarded user opening /onboarding is sent to chat", async ({ page, request }) => {
    await signIn(page, await createAccount(request));
    await page.goto("/onboarding");
    await expect(page).toHaveURL(/\/chat\//);
  });

  test("A5 an unknown address for a logged-in user goes to chat", async ({ page, request }) => {
    await signIn(page, await createAccount(request));
    await page.goto("/no-such-page");
    await expect(page).toHaveURL(/\/chat\//);
  });

  test("A6 a broken or expired login token sends the user back to login", async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem("mynaksh_token", "not-a-real-token"));
    await page.goto("/chat");
    await expect(page).toHaveURL(/\/login$/);
    expect(await page.evaluate(() => localStorage.getItem("mynaksh_token"))).toBeNull();
  });
});
