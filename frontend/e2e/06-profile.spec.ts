// G. Viewing and editing the profile.

import { expect, test } from "@playwright/test";

import { createAccount, signIn } from "./helpers";

test.describe("G. Profile", () => {
  test("G1 the profile page shows the email, the sun sign and the saved details", async ({ page, request }) => {
    const account = await createAccount(request, { profile: { birth_time: "14:30", birth_time_known: true } });
    await signIn(page, account);
    await page.goto("/profile");
    await expect(page.getByText(account.email)).toBeVisible();
    await expect(page.getByText("Leo · Fire")).toBeVisible();
    await expect(page.getByText("confident, generous, expressive")).toBeVisible();
    await expect(page.getByLabel("Name")).toHaveValue("Rahul");
    await expect(page.getByLabel("Date of birth")).toHaveValue("1995-08-15");
    await expect(page.getByLabel("Time of birth")).toHaveValue("14:30");
    await expect(page.getByLabel("Place of birth")).toHaveValue("Delhi");
    await expect(page.getByLabel("I don't know my birth time")).not.toBeChecked();
  });

  test("G2 editing the name saves it, and it is still there after a reload", async ({ page, request }) => {
    await signIn(page, await createAccount(request));
    await page.goto("/profile");
    await page.getByLabel("Name").fill("Rahul Sharma");
    await page.getByRole("button", { name: "Save changes" }).click();
    await expect(page.getByText("Profile saved.")).toBeVisible();
    await page.reload();
    await expect(page.getByLabel("Name")).toHaveValue("Rahul Sharma");
  });

  test("G3 changing the date of birth changes the sun sign", async ({ page, request }) => {
    await signIn(page, await createAccount(request));
    await page.goto("/profile");
    await expect(page.getByText("Leo · Fire")).toBeVisible();
    await page.getByLabel("Date of birth").fill("1995-03-25");
    await page.getByRole("button", { name: "Save changes" }).click();
    await expect(page.getByText("Profile saved.")).toBeVisible();
    await expect(page.getByText("Aries · Fire")).toBeVisible();
    await expect(page.getByText("Leo · Fire")).toBeHidden();
  });

  test("G4 a birth time can be added later, and removed again", async ({ page, request }) => {
    await signIn(page, await createAccount(request)); // starts with the birth time unknown
    await page.goto("/profile");
    await expect(page.getByLabel("I don't know my birth time")).toBeChecked();
    await expect(page.getByLabel("Time of birth")).toBeDisabled();

    await page.getByLabel("I don't know my birth time").uncheck();
    await page.getByLabel("Time of birth").fill("09:15");
    await page.getByRole("button", { name: "Save changes" }).click();
    await expect(page.getByText("Profile saved.")).toBeVisible();
    await page.reload();
    await expect(page.getByLabel("Time of birth")).toHaveValue("09:15");

    await page.getByLabel("I don't know my birth time").check();
    await page.getByRole("button", { name: "Save changes" }).click();
    await expect(page.getByText("Profile saved.")).toBeVisible();
    await page.reload();
    await expect(page.getByLabel("I don't know my birth time")).toBeChecked();
    await expect(page.getByLabel("Time of birth")).toHaveValue("");
  });

  test("G5 an invalid edit shows an error and saves nothing", async ({ page, request }) => {
    await signIn(page, await createAccount(request));
    await page.goto("/profile");
    await page.getByLabel("Place of birth").fill("   ");
    await page.getByRole("button", { name: "Save changes" }).click();
    await expect(page.getByRole("alert")).toContainText("cannot be empty");
    await expect(page.getByText("Profile saved.")).toBeHidden();
    await page.reload();
    await expect(page.getByLabel("Place of birth")).toHaveValue("Delhi");
  });
});
