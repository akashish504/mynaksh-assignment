// E. The chat window: sending, sessions, memory indicator, and failures.

import { expect, test } from "@playwright/test";

import {
  API_URL,
  CHIP_TIMEOUT,
  composer,
  createAccount,
  createSession,
  newChatButton,
  openChat,
  sendMessage,
  signIn,
} from "./helpers";

const DURABLE_FACT = "I'm planning to switch jobs next year.";

test.describe("E. Chat", () => {
  test("E1 the first visit creates a chat and shows the empty state", async ({ page, request }) => {
    await signIn(page, await createAccount(request));
    await openChat(page);
    await expect(page.getByText("Ask me anything")).toBeVisible();
    await expect(page.getByTestId("session-item")).toHaveCount(1);
    await expect(page.getByTestId("session-item")).toHaveText("New chat");
    await expect(page.getByRole("button", { name: "Send" })).toBeDisabled();
  });

  test("E2 Enter sends the message, shows a waiting state, then the reply", async ({ page, request }) => {
    await signIn(page, await createAccount(request));
    await openChat(page);
    await composer(page).fill("Hello!");
    await composer(page).press("Enter");

    await expect(page.getByTestId("message-user")).toHaveText("Hello!"); // shown straight away
    await expect(page.getByTestId("thinking")).toBeVisible();
    await expect(composer(page)).toHaveValue(""); // the box is cleared
    await expect(page.getByTestId("message-assistant")).toHaveCount(1, { timeout: 60_000 });
    await expect(page.getByTestId("thinking")).toBeHidden();
    expect((await page.getByTestId("message-assistant").innerText()).length).toBeGreaterThan(10);
    await expect(page.getByText("Ask me anything")).toBeHidden();
  });

  test("E3 the Send button works and is disabled for an empty or blank message", async ({ page, request }) => {
    await signIn(page, await createAccount(request));
    await openChat(page);
    const send = page.getByRole("button", { name: "Send" });

    await composer(page).fill("    ");
    await expect(send).toBeDisabled();
    await composer(page).press("Enter"); // a blank message is not sent
    await expect(page.getByTestId("message-user")).toHaveCount(0);

    await composer(page).fill("Hello!");
    await expect(send).toBeEnabled();
    await send.click();
    await expect(page.getByTestId("message-assistant")).toHaveCount(1, { timeout: 60_000 });
  });

  test("E4 Shift+Enter adds a new line, and line breaks are kept in the bubble", async ({ page, request }) => {
    await signIn(page, await createAccount(request));
    await openChat(page);
    await composer(page).fill("First line");
    await composer(page).press("Shift+Enter");
    await composer(page).pressSequentially("Second line");
    await expect(page.getByTestId("message-user")).toHaveCount(0); // not sent yet
    await expect(composer(page)).toHaveValue("First line\nSecond line");

    await composer(page).press("Enter");
    await expect(page.getByTestId("message-user")).toHaveText("First line\nSecond line");
    await expect(page.getByTestId("message-user")).toHaveCSS("white-space", "pre-wrap");
    await expect(page.getByTestId("message-assistant")).toHaveCount(1, { timeout: 60_000 });
  });

  test("E5 the message box does not accept more than 2,000 characters", async ({ page, request }) => {
    await signIn(page, await createAccount(request));
    await openChat(page);
    await expect(composer(page)).toHaveAttribute("maxlength", "2000");
  });

  test("E6 the chat takes its title from the first message and keeps it", async ({ page, request }) => {
    await signIn(page, await createAccount(request));
    await openChat(page);
    await sendMessage(page, "What does this month look like for me?");
    await expect(page.getByTestId("session-item")).toHaveText("What does this month look like for me?");
    await sendMessage(page, "And next month?");
    await expect(page.getByTestId("session-item")).toHaveText("What does this month look like for me?");
  });

  test("E7 a follow-up question gets an answer in the same conversation", async ({ page, request }) => {
    await signIn(page, await createAccount(request));
    await openChat(page);
    await sendMessage(page, "What should I focus on in my career?");
    const followUp = await sendMessage(page, "Why do you say that?");
    expect(followUp.length).toBeGreaterThan(20);
    await expect(page.getByTestId("message-user")).toHaveCount(2);
    await expect(page.getByTestId("message-assistant")).toHaveCount(2);
  });

  test("E8 New chat starts an empty chat; switching back restores each history", async ({ page, request }) => {
    await signIn(page, await createAccount(request));
    await openChat(page);
    await sendMessage(page, "Hello from the first chat");
    const firstUrl = page.url();

    await newChatButton(page).click();
    await expect(page).not.toHaveURL(firstUrl);
    await expect(page.getByText("Ask me anything")).toBeVisible();
    await expect(page.getByTestId("message-user")).toHaveCount(0);
    await expect(page.getByTestId("session-item")).toHaveCount(2);

    await sendMessage(page, "Hello from the second chat");
    // The chat that was just used is at the top of the list.
    await expect(page.getByTestId("session-item").first()).toHaveText("Hello from the second chat");

    await page.getByTestId("session-item").filter({ hasText: "Hello from the first chat" }).click();
    await expect(page).toHaveURL(firstUrl);
    await expect(page.getByTestId("message-user")).toHaveText("Hello from the first chat");
    await expect(page.getByTestId("message-assistant")).toHaveCount(1);
  });

  test("E9 reloading the page keeps the conversation and the chat list", async ({ page, request }) => {
    await signIn(page, await createAccount(request));
    await openChat(page);
    await sendMessage(page, "Remember this conversation");
    const url = page.url();

    await page.reload();
    await expect(page).toHaveURL(url);
    await expect(page.getByTestId("message-user")).toHaveText("Remember this conversation");
    await expect(page.getByTestId("message-assistant")).toHaveCount(1);
    await expect(page.getByTestId("session-item")).toHaveText("Remember this conversation");
  });

  test("E10 opening /chat goes to the most recently used chat", async ({ page, request }) => {
    await signIn(page, await createAccount(request));
    await openChat(page);
    await sendMessage(page, "The older chat");
    await newChatButton(page).click();
    await expect(page.getByText("Ask me anything")).toBeVisible();
    await sendMessage(page, "The newer chat");
    const newest = page.url();

    await openChat(page, "/chat");
    await expect(page).toHaveURL(newest);
  });

  test("E11 a chat address that belongs to someone else, or does not exist, is not shown", async ({ page, request }) => {
    const owner = await createAccount(request);
    const othersSession = await createSession(request, owner);
    await signIn(page, await createAccount(request));

    await page.goto(`/chat/${othersSession}`);
    await expect(page).not.toHaveURL(new RegExp(othersSession), { timeout: 20_000 });
    await expect(page).toHaveURL(/\/chat\/[0-9a-f-]{36}$/);

    await page.goto("/chat/00000000-0000-0000-0000-000000000000");
    await expect(page).not.toHaveURL(/00000000-0000/, { timeout: 20_000 });
  });

  test("E12 a lasting fact produces a 'Memory updated' chip that opens the memory page", async ({ page, request }) => {
    await signIn(page, await createAccount(request));
    await openChat(page);
    await sendMessage(page, DURABLE_FACT);

    const chip = page.getByTestId("memory-chip");
    await expect(chip).toBeVisible({ timeout: CHIP_TIMEOUT });
    await expect(chip).toContainText(/^Memory updated: Career/);

    await chip.click();
    await expect(page).toHaveURL(/\/memory$/);
    await expect(page.getByRole("heading", { name: "Career" })).toBeVisible();
    await expect(page.getByTestId("memory-card")).toHaveCount(1);
  });

  test("E13 an ordinary question produces no memory chip", async ({ page, request }) => {
    await signIn(page, await createAccount(request));
    await openChat(page);
    await sendMessage(page, "What is my zodiac sign?");
    await page.waitForTimeout(10_000); // longer than the 8 seconds of polling
    await expect(page.getByTestId("memory-chip")).toHaveCount(0);
  });

  test("E14 a later question is answered using the remembered fact", async ({ page, request }) => {
    await signIn(page, await createAccount(request));
    await openChat(page);
    await sendMessage(page, DURABLE_FACT);
    await expect(page.getByTestId("memory-chip")).toBeVisible({ timeout: CHIP_TIMEOUT });

    // A brand-new chat: nothing is carried over except what was remembered.
    await newChatButton(page).click();
    await expect(page.getByText("Ask me anything")).toBeVisible();
    const reply = await sendMessage(page, "What do you remember about my career goals?");
    expect(reply.toLowerCase()).toMatch(/switch|job/);
  });

  test("E15 correcting a profile detail in chat shows 'Profile updated' and changes the profile", async ({ page, request }) => {
    await signIn(page, await createAccount(request));
    await openChat(page);
    await sendMessage(page, "Correction to my profile: my place of birth is Mumbai, not Delhi.");

    const chip = page.getByTestId("memory-chip").filter({ hasText: "Profile updated" });
    await expect(chip).toBeVisible({ timeout: CHIP_TIMEOUT });
    await expect(chip).toContainText("Birth place updated");

    await chip.click();
    await expect(page).toHaveURL(/\/profile$/);
    await expect(page.getByLabel("Place of birth")).toHaveValue(/Mumbai/);
  });

  test("E16 when the server cannot be reached, the message is kept and an error is shown", async ({ page, request }) => {
    await signIn(page, await createAccount(request));
    await openChat(page);
    await page.route(`${API_URL}/chat`, (route) => route.abort());

    await composer(page).fill("This will not go through");
    await composer(page).press("Enter");

    await expect(page.getByRole("alert")).toContainText("Could not reach the server");
    await expect(composer(page)).toHaveValue("This will not go through"); // nothing typed is lost
    await expect(page.getByTestId("message-user")).toHaveCount(0);
    await expect(page.getByTestId("thinking")).toBeHidden();

    // After the connection is back, the same message can be sent.
    await page.unroute(`${API_URL}/chat`);
    await composer(page).press("Enter");
    await expect(page.getByTestId("message-assistant")).toHaveCount(1, { timeout: 60_000 });
    await expect(page.getByRole("alert")).toBeHidden();
  });

  test("E17 sending too fast shows the rate-limit message", async ({ page, request }) => {
    await signIn(page, await createAccount(request));
    await openChat(page);
    await page.route(`${API_URL}/chat`, (route) =>
      route.fulfill({
        status: 429,
        contentType: "application/json",
        headers: { "access-control-allow-origin": "*" },
        body: JSON.stringify({ detail: "You're sending messages too quickly. Please wait a moment and try again." }),
      }),
    );
    await composer(page).fill("One message too many");
    await composer(page).press("Enter");
    await expect(page.getByRole("alert")).toContainText("too quickly");
    await expect(composer(page)).toHaveValue("One message too many");
  });

  test("E18 a reply that takes more than 3 seconds shows Connecting", async ({ page, request }) => {
    await signIn(page, await createAccount(request));
    await openChat(page);
    await page.route(`${API_URL}/chat`, async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 4000));
      await route.continue();
    });
    await composer(page).fill("Hello!");
    await composer(page).press("Enter");
    await expect(page.getByTestId("thinking")).toHaveText("Thinking…");
    await expect(page.getByTestId("thinking")).toHaveText("Connecting…", { timeout: 6000 });
    await expect(page.getByTestId("message-assistant")).toHaveCount(1, { timeout: 60_000 });
  });

  test("E19 a second message cannot be sent while the first is still being answered", async ({ page, request }) => {
    await signIn(page, await createAccount(request));
    await openChat(page);
    await composer(page).fill("First message");
    await composer(page).press("Enter");
    await composer(page).fill("Second message typed while waiting");
    await expect(page.getByRole("button", { name: "Send" })).toBeDisabled();
    await composer(page).press("Enter");
    await expect(page.getByTestId("message-user")).toHaveCount(1);
    await expect(page.getByTestId("message-assistant")).toHaveCount(1, { timeout: 60_000 });
    // The typed text is still there and can be sent now.
    await expect(composer(page)).toHaveValue("Second message typed while waiting");
    await expect(page.getByRole("button", { name: "Send" })).toBeEnabled();
  });

  test("E20 a reply that arrives after switching chats does not appear in the other chat", async ({ page, request }) => {
    await signIn(page, await createAccount(request));
    await openChat(page);
    const firstUrl = page.url();
    // Hold the reply back long enough to switch chats while it is on its way.
    await page.route(`${API_URL}/chat`, async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 3000));
      await route.continue();
    });
    await composer(page).fill("A question in the first chat");
    await composer(page).press("Enter");
    await expect(page.getByTestId("thinking")).toBeVisible();

    // Start waiting for the held-back reply before switching, so it cannot be missed.
    const answered = page.waitForResponse((response) => response.url() === `${API_URL}/chat`, { timeout: 60_000 });
    // The first chat is still titled "New chat" in the list, so pick the real button.
    await newChatButton(page).click();
    await expect(page).not.toHaveURL(firstUrl);
    await answered;
    await page.waitForTimeout(1000);

    // The new chat stays empty...
    await expect(page.getByTestId("message-user")).toHaveCount(0);
    await expect(page.getByTestId("message-assistant")).toHaveCount(0);

    // ...and the question and its answer are in the chat they belong to.
    await page.getByTestId("session-item").filter({ hasText: "A question in the first chat" }).click();
    await expect(page).toHaveURL(firstUrl);
    await expect(page.getByTestId("message-user")).toHaveText("A question in the first chat");
    await expect(page.getByTestId("message-assistant")).toHaveCount(1);
  });
});
