// D. The birth-details form shown once after signup.

import { expect, test } from "@playwright/test";

import { createAccount, navLink, signIn } from "./helpers";

test.describe("D. Onboarding", () => {
  test.beforeEach(async ({ page, request }) => {
    await signIn(page, await createAccount(request, { onboarded: false }));
    await page.goto("/onboarding");
    await expect(page.getByRole("heading", { name: "Your birth details" })).toBeVisible();
  });

  test("D1 with a known birth time, the profile is saved and chat opens", async ({ page }) => {
    await page.getByLabel("Name").fill("Priya");
    await page.getByLabel("Date of birth").fill("1998-03-25");
    await page.getByLabel("Time of birth").fill("06:45");
    await page.getByLabel("Place of birth").fill("Pune");
    await page.getByRole("button", { name: "Continue" }).click();
    await expect(page).toHaveURL(/\/chat\//);

    await navLink(page, "Profile").click();
    await expect(page.getByLabel("Name")).toHaveValue("Priya");
    await expect(page.getByLabel("Time of birth")).toHaveValue("06:45");
    await expect(page.getByText("Aries · Fire")).toBeVisible(); // worked out from the date of birth
  });

  test("D2 ticking 'I don't know my birth time' disables the time and saves it as unknown", async ({ page }) => {
    await page.getByLabel("Name").fill("Rahul");
    await page.getByLabel("Date of birth").fill("1995-08-15");
    await page.getByLabel("Time of birth").fill("14:30");
    await page.getByLabel("I don't know my birth time").check();
    await expect(page.getByLabel("Time of birth")).toBeDisabled();
    await expect(page.getByLabel("Time of birth")).toHaveValue("");
    await page.getByLabel("Place of birth").fill("Delhi");
    await page.getByRole("button", { name: "Continue" }).click();
    await expect(page).toHaveURL(/\/chat\//);

    await navLink(page, "Memory").click();
    await expect(page.getByText("Unknown", { exact: true })).toBeVisible();
    await expect(page.getByText("Leo (Fire)")).toBeVisible();
  });

  test("D3 unticking the checkbox makes the time required again", async ({ page }) => {
    await page.getByLabel("I don't know my birth time").check();
    await page.getByLabel("I don't know my birth time").uncheck();
    await expect(page.getByLabel("Time of birth")).toBeEnabled();
    await page.getByLabel("Name").fill("Rahul");
    await page.getByLabel("Date of birth").fill("1995-08-15");
    await page.getByLabel("Place of birth").fill("Delhi");
    await page.getByRole("button", { name: "Continue" }).click();
    await expect(page).toHaveURL(/\/onboarding$/); // no time given, so the form does not submit
  });

  test("D4 leaving a required field empty keeps the user on the form", async ({ page }) => {
    await page.getByLabel("Date of birth").fill("1995-08-15");
    await page.getByLabel("I don't know my birth time").check();
    await page.getByLabel("Place of birth").fill("Delhi");
    await page.getByRole("button", { name: "Continue" }).click(); // name is empty
    await expect(page).toHaveURL(/\/onboarding$/);
  });

  test("D5 a date of birth in the future is not accepted", async ({ page }) => {
    await page.getByLabel("Name").fill("Rahul");
    await page.getByLabel("Date of birth").fill("2999-01-01");
    await page.getByLabel("I don't know my birth time").check();
    await page.getByLabel("Place of birth").fill("Delhi");
    await page.getByRole("button", { name: "Continue" }).click();
    await expect(page).toHaveURL(/\/onboarding$/);
  });

  test("D6 a name of only spaces is rejected by the server with a readable message", async ({ page }) => {
    await page.getByLabel("Name").fill("   ");
    await page.getByLabel("Date of birth").fill("1995-08-15");
    await page.getByLabel("I don't know my birth time").check();
    await page.getByLabel("Place of birth").fill("Delhi");
    await page.getByRole("button", { name: "Continue" }).click();
    await expect(page.getByRole("alert")).toContainText("cannot be empty");
    await expect(page).toHaveURL(/\/onboarding$/);
  });

  test("D7 the user can log out from onboarding", async ({ page }) => {
    await page.addInitScript(() => localStorage.removeItem("mynaksh_token"));
    await page.getByRole("button", { name: "Log out" }).click();
    await expect(page).toHaveURL(/\/login$/);
  });
});
