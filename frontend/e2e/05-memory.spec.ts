// F. The memory page: what is shown, and deleting.

import { expect, test } from "@playwright/test";

import {
  CHIP_TIMEOUT,
  createAccount,
  getMemoryPage,
  navLink,
  openChat,
  sendMessage,
  signIn,
} from "./helpers";

test.describe("F. Memory page", () => {
  test("F1 a new user sees their profile summary and an empty memory list", async ({ page, request }) => {
    await signIn(page, await createAccount(request, { profile: { birth_time: "14:30", birth_time_known: true } }));
    await page.goto("/memory");
    await expect(page.getByRole("heading", { name: "What I remember about you" })).toBeVisible();
    await expect(page.getByText("Rahul", { exact: true })).toBeVisible();
    await expect(page.getByText("Delhi", { exact: true })).toBeVisible();
    await expect(page.getByText("14:30", { exact: true })).toBeVisible();
    await expect(page.getByText("Leo (Fire)")).toBeVisible();
    await expect(page.getByText("Nothing stored yet.")).toBeVisible();
    await expect(page.getByTestId("memory-card")).toHaveCount(0);
  });

  test("F2 an unknown birth time is shown as Unknown", async ({ page, request }) => {
    await signIn(page, await createAccount(request));
    await page.goto("/memory");
    await expect(page.getByText("Unknown", { exact: true })).toBeVisible();
  });

  test("F3 a remembered fact appears under its life area, with its kind and date", async ({ page, request }) => {
    const account = await createAccount(request);
    await signIn(page, account);
    await openChat(page);
    await sendMessage(page, "I'm planning to switch jobs next year.");
    await expect(page.getByTestId("memory-chip")).toBeVisible({ timeout: CHIP_TIMEOUT });

    await navLink(page, "Memory").click();
    await expect(page.getByRole("heading", { name: "Career" })).toBeVisible();
    const card = page.getByTestId("memory-card");
    await expect(card).toHaveCount(1);
    await expect(card).toContainText("Goal");
    await expect(card).toContainText(/Saved /);
    await expect(card).toContainText(/job/i);
    await expect(page.getByText("Nothing stored yet.")).toBeHidden();
  });

  test("F4 cancelling a delete keeps the memory; confirming removes it for good", async ({ page, request }) => {
    const account = await createAccount(request);
    await signIn(page, account);
    await openChat(page);
    await sendMessage(page, "I'm planning to switch jobs next year.");
    await expect(page.getByTestId("memory-chip")).toBeVisible({ timeout: CHIP_TIMEOUT });
    await navLink(page, "Memory").click();
    await expect(page.getByTestId("memory-card")).toHaveCount(1);

    // Cancel
    await page.getByRole("button", { name: /^Delete memory/ }).click();
    await expect(page.getByRole("dialog")).toContainText("Delete this memory?");
    await expect(page.getByRole("dialog")).toContainText("This cannot be undone.");
    await page.getByRole("button", { name: "Cancel" }).click();
    await expect(page.getByRole("dialog")).toBeHidden();
    await expect(page.getByTestId("memory-card")).toHaveCount(1);

    // Confirm
    await page.getByRole("button", { name: /^Delete memory/ }).click();
    await page.getByRole("button", { name: "Delete", exact: true }).click();
    await expect(page.getByTestId("memory-card")).toHaveCount(0);
    await expect(page.getByText("Nothing stored yet.")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Career" })).toBeHidden();

    // Still gone after a reload, and gone on the server.
    await page.reload();
    await expect(page.getByText("Nothing stored yet.")).toBeVisible();
    expect((await getMemoryPage(request, account)).memories).toEqual({});
  });

  test("F5 facts from different life areas are grouped separately", async ({ page, request }) => {
    const account = await createAccount(request);
    await signIn(page, account);
    await openChat(page);
    await sendMessage(page, "I'm planning to switch jobs next year.");
    await expect(page.getByTestId("memory-chip")).toHaveCount(1, { timeout: CHIP_TIMEOUT });
    await sendMessage(page, "I have started running every morning to improve my health.");
    await expect(page.getByTestId("memory-chip")).toHaveCount(2, { timeout: CHIP_TIMEOUT });

    await navLink(page, "Memory").click();
    await expect(page.getByRole("heading", { name: "Career" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Health" })).toBeVisible();
    await expect(page.getByTestId("memory-card")).toHaveCount(2);
  });
});
