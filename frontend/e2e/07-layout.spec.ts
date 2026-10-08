// H. Navigation, phone layout, and keeping users apart.

import { expect, test } from "@playwright/test";

import {
  CHIP_TIMEOUT,
  composer,
  createAccount,
  logInThroughForm,
  navLink,
  newChatButton,
  openChat,
  sendMessage,
  signIn,
} from "./helpers";

test.describe("H. Navigation and layout", () => {
  test("H1 the top bar moves between Chat, Memory and Profile and marks the current page", async ({ page, request }) => {
    await signIn(page, await createAccount(request));
    await openChat(page);

    await navLink(page, "Memory").click();
    await expect(page).toHaveURL(/\/memory$/);
    await expect(navLink(page, "Memory")).toHaveAttribute("aria-current", "page");

    await navLink(page, "Profile").click();
    await expect(page).toHaveURL(/\/profile$/);
    await expect(navLink(page, "Profile")).toHaveAttribute("aria-current", "page");

    await navLink(page, "Chat").click();
    await expect(page).toHaveURL(/\/chat\//);
    await expect(navLink(page, "Chat")).toHaveAttribute("aria-current", "page");
  });

  test("H2 the browser's back and forward buttons work", async ({ page, request }) => {
    await signIn(page, await createAccount(request));
    await openChat(page);
    const chatUrl = page.url();
    await navLink(page, "Memory").click();
    await expect(page).toHaveURL(/\/memory$/);
    await navLink(page, "Profile").click();
    await expect(page).toHaveURL(/\/profile$/);

    await page.goBack();
    await expect(page.getByRole("heading", { name: "What I remember about you" })).toBeVisible();
    await page.goBack();
    await expect(page).toHaveURL(chatUrl);
    await page.goForward();
    await expect(page).toHaveURL(/\/memory$/);
  });

  test("H3 on a phone the chat list is a drawer, and everything fits the screen", async ({ page, request }) => {
    await page.setViewportSize({ width: 390, height: 780 });
    await signIn(page, await createAccount(request));
    await openChat(page);

    // The permanent sidebar is hidden; the list is reached through a button.
    await expect(page.locator("aside")).toBeHidden();
    await sendMessage(page, "Hello from my phone");
    await page.getByRole("button", { name: "Open chats" }).click();
    await expect(newChatButton(page)).toBeVisible();
    await newChatButton(page).click();
    await expect(page.getByText("Ask me anything")).toBeVisible(); // the drawer closed and a new chat opened
    await expect(newChatButton(page)).toHaveCount(0);

    // Choosing a chat from the drawer opens it and closes the drawer.
    await page.getByRole("button", { name: "Open chats" }).click();
    // The hidden sidebar holds a second copy of the list, so pick the visible one.
    await page.locator('[data-testid="session-item"]:visible').filter({ hasText: "Hello from my phone" }).click();
    await expect(page.getByTestId("message-user")).toHaveText("Hello from my phone");
    await expect(newChatButton(page)).toHaveCount(0);

    for (const path of ["/memory", "/profile"]) {
      await page.goto(path);
      await expect(page.getByRole("button", { name: "Log out" })).toBeVisible();
      const overflows = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
      expect(overflows, `${path} should not scroll sideways`).toBe(false);
    }
  });

  test("H4 a long reply scrolls inside the chat and the message box stays visible", async ({ page, request }) => {
    await signIn(page, await createAccount(request));
    await openChat(page);
    for (const text of ["Tell me about my career.", "And my health?", "And my relationships?"]) {
      await sendMessage(page, text);
    }
    await expect(composer(page)).toBeInViewport();
    await expect(page.getByTestId("message-assistant").last()).toBeInViewport(); // scrolled to the newest
  });
});

test.describe("I. Keeping users apart", () => {
  test("I1 one user never sees another user's chats or memories", async ({ browser, request }) => {
    const rahul = await createAccount(request);
    const priya = await createAccount(request, { profile: { name: "Priya", dob: "1998-03-25", birth_place: "Pune" } });

    const rahulPage = await (await browser.newContext()).newPage();
    await signIn(rahulPage, rahul);
    await openChat(rahulPage);
    await sendMessage(rahulPage, "I'm planning to switch jobs next year.");
    await expect(rahulPage.getByTestId("memory-chip")).toBeVisible({ timeout: CHIP_TIMEOUT });

    const priyaPage = await (await browser.newContext()).newPage();
    await signIn(priyaPage, priya);
    await openChat(priyaPage);
    await expect(priyaPage.getByTestId("session-item")).toHaveCount(1);
    await expect(priyaPage.getByTestId("session-item")).toHaveText("New chat");
    await expect(priyaPage.getByText("switch jobs")).toHaveCount(0);

    await priyaPage.goto("/memory");
    await expect(priyaPage.getByText("Priya", { exact: true })).toBeVisible();
    await expect(priyaPage.getByText("Nothing stored yet.")).toBeVisible();
    await expect(priyaPage.getByTestId("memory-card")).toHaveCount(0);
  });

  test("I2 logging out and in as someone else shows only the new user's data", async ({ page, request }) => {
    const rahul = await createAccount(request);
    const priya = await createAccount(request, { profile: { name: "Priya", dob: "1998-03-25", birth_place: "Pune" } });

    await logInThroughForm(page, rahul.email);
    await expect(page).toHaveURL(/\/chat\//);
    await expect(page.getByText("Loading chat")).toBeHidden();
    await sendMessage(page, "A message only Rahul should see");
    await page.getByRole("button", { name: "Log out" }).click();
    await expect(page).toHaveURL(/\/login$/);

    await logInThroughForm(page, priya.email);
    await expect(page).toHaveURL(/\/chat\//);
    await expect(page.getByText("Loading chat")).toBeHidden();
    await expect(page.getByText("A message only Rahul should see")).toHaveCount(0);
    await navLink(page, "Profile").click();
    await expect(page.getByText(priya.email)).toBeVisible();
    await expect(page.getByLabel("Name")).toHaveValue("Priya");
  });
});
