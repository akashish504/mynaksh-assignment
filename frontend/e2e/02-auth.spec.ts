// B and C. Signing up, logging in, staying logged in, logging out.

import { expect, test } from "@playwright/test";

import { API_URL, PASSWORD, createAccount, logInThroughForm, signIn, uniqueEmail } from "./helpers";

test.describe("B. Signup", () => {
  test("B1 signing up leads to onboarding", async ({ page }) => {
    await page.goto("/signup");
    await expect(page.getByText("Create your account")).toBeVisible();
    await page.getByLabel("Email").fill(uniqueEmail());
    await page.getByLabel("Password").fill(PASSWORD);
    await page.getByRole("button", { name: "Sign up" }).click();
    await expect(page).toHaveURL(/\/onboarding$/);
  });

  test("B2 an email that is already registered shows an error", async ({ page, request }) => {
    const existing = await createAccount(request);
    await page.goto("/signup");
    await page.getByLabel("Email").fill(existing.email.toUpperCase()); // same email, different case
    await page.getByLabel("Password").fill(PASSWORD);
    await page.getByRole("button", { name: "Sign up" }).click();
    await expect(page.getByRole("alert")).toContainText("already exists");
    await expect(page).toHaveURL(/\/signup$/);
  });

  test("B3 an invalid email is stopped by the form", async ({ page }) => {
    let signupCalls = 0;
    await page.route(`${API_URL}/auth/signup`, (route) => {
      signupCalls += 1;
      return route.continue();
    });
    await page.goto("/signup");
    await page.getByLabel("Email").fill("not-an-email");
    await page.getByLabel("Password").fill(PASSWORD);
    await page.getByRole("button", { name: "Sign up" }).click();
    await expect(page).toHaveURL(/\/signup$/);
    expect(signupCalls).toBe(0);
  });

  test("B4 a password shorter than 8 characters is stopped by the form", async ({ page }) => {
    let signupCalls = 0;
    await page.route(`${API_URL}/auth/signup`, (route) => {
      signupCalls += 1;
      return route.continue();
    });
    await page.goto("/signup");
    await expect(page.getByText("At least 8 characters")).toBeVisible();
    await page.getByLabel("Email").fill(uniqueEmail());
    await page.getByLabel("Password").fill("short");
    await page.getByRole("button", { name: "Sign up" }).click();
    await expect(page).toHaveURL(/\/signup$/);
    expect(signupCalls).toBe(0);
  });

  test("B5 the login and signup pages link to each other", async ({ page }) => {
    await page.goto("/login");
    await page.getByRole("link", { name: "Create an account" }).click();
    await expect(page).toHaveURL(/\/signup$/);
    await page.getByRole("link", { name: "Log in" }).click();
    await expect(page).toHaveURL(/\/login$/);
    await expect(page.getByText("Welcome back")).toBeVisible();
  });
});

test.describe("C. Login and logout", () => {
  test("C1 an onboarded user logs in and lands on chat", async ({ page, request }) => {
    const account = await createAccount(request);
    await logInThroughForm(page, account.email);
    await expect(page).toHaveURL(/\/chat\//);
  });

  test("C2 a user who has not onboarded logs in and lands on onboarding", async ({ page, request }) => {
    const account = await createAccount(request, { onboarded: false });
    await logInThroughForm(page, account.email);
    await expect(page).toHaveURL(/\/onboarding$/);
  });

  test("C3 the email is not case-sensitive at login", async ({ page, request }) => {
    const account = await createAccount(request);
    await logInThroughForm(page, account.email.toUpperCase());
    await expect(page).toHaveURL(/\/chat\//);
  });

  test("C4 a wrong password and an unknown email show the same error", async ({ page, request }) => {
    const account = await createAccount(request);

    await logInThroughForm(page, account.email, "wrong-password");
    await expect(page.getByRole("alert")).toHaveText("Incorrect email or password.");
    await expect(page).toHaveURL(/\/login$/);

    await logInThroughForm(page, uniqueEmail());
    await expect(page.getByRole("alert")).toHaveText("Incorrect email or password.");
  });

  test("C5 the login survives a page reload", async ({ page, request }) => {
    const account = await createAccount(request);
    await logInThroughForm(page, account.email);
    await expect(page).toHaveURL(/\/chat\//);
    await page.reload();
    await expect(page).toHaveURL(/\/chat\//);
    await expect(page.getByRole("button", { name: "Log out" })).toBeVisible();
  });

  test("C6 logging out returns to login and protects the pages again", async ({ page, request }) => {
    await signIn(page, await createAccount(request));
    await page.goto("/memory");
    await expect(page.getByRole("heading", { name: "What I remember about you" })).toBeVisible();

    // signIn() re-adds the token on every page load, so remove that before logging out.
    await page.addInitScript(() => localStorage.removeItem("mynaksh_token"));
    await page.getByRole("button", { name: "Log out" }).click();
    await expect(page).toHaveURL(/\/login$/);

    await page.goto("/memory");
    await expect(page).toHaveURL(/\/login$/);
    await page.goBack();
    await expect(page.getByRole("heading", { name: "What I remember about you" })).toBeHidden();
  });

  test("C7 a slow login shows Connecting", async ({ page, request }) => {
    const account = await createAccount(request);
    await page.route(`${API_URL}/auth/login`, async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 4000));
      await route.continue();
    });
    await logInThroughForm(page, account.email);
    await expect(page.getByRole("button", { name: "Connecting…" })).toBeVisible({ timeout: 5000 });
    await expect(page).toHaveURL(/\/chat\//);
  });

  test("C8 when the server cannot be reached, login says so", async ({ page, request }) => {
    const account = await createAccount(request);
    await page.route(`${API_URL}/auth/login`, (route) => route.abort());
    await logInThroughForm(page, account.email);
    await expect(page.getByRole("alert")).toContainText("Could not reach the server");
  });
});
