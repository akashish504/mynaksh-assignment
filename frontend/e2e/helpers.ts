// Shared helpers for the browser tests.

import { expect } from "@playwright/test";
import type { APIRequestContext, Page } from "@playwright/test";

export const API_URL = process.env.E2E_API_URL ?? "http://localhost:8000";
export const PASSWORD = "correct-horse";

// How long to wait for a real model to answer.
export const REPLY_TIMEOUT = 60_000;
// The memory indicator is polled for up to 8 seconds after the reply.
export const CHIP_TIMEOUT = 20_000;

export interface Account {
  email: string;
  token: string;
}

export interface ProfileInput {
  name?: string;
  dob?: string;
  birth_time?: string | null;
  birth_time_known?: boolean;
  birth_place?: string;
}

let counter = 0;
export function uniqueEmail(): string {
  counter += 1;
  return `e2e-${Date.now()}-${process.pid}-${counter}@example.com`;
}

function authHeader(token: string) {
  return { Authorization: `Bearer ${token}` };
}

// Create an account through the API. Faster than clicking through signup, for
// the tests that are about something else.
export async function createAccount(
  request: APIRequestContext,
  options: { onboarded?: boolean; profile?: ProfileInput; email?: string } = {},
): Promise<Account> {
  const email = options.email ?? uniqueEmail();
  const signup = await request.post(`${API_URL}/auth/signup`, { data: { email, password: PASSWORD } });
  expect(signup.status(), await signup.text()).toBe(201);
  const token = (await signup.json()).access_token as string;

  if (options.onboarded ?? true) {
    const profile = {
      name: "Rahul",
      dob: "1995-08-15",
      birth_time: null,
      birth_time_known: false,
      birth_place: "Delhi",
      ...options.profile,
    };
    const saved = await request.put(`${API_URL}/users/me/profile`, { data: profile, headers: authHeader(token) });
    expect(saved.status(), await saved.text()).toBe(200);
  }
  return { email, token };
}

export async function createSession(request: APIRequestContext, account: Account): Promise<string> {
  const response = await request.post(`${API_URL}/sessions`, { headers: authHeader(account.token) });
  expect(response.status()).toBe(201);
  return (await response.json()).id as string;
}

export async function getMemoryPage(request: APIRequestContext, account: Account) {
  const response = await request.get(`${API_URL}/users/me/memory`, { headers: authHeader(account.token) });
  return response.json();
}

// Make the browser start out logged in as this account.
export async function signIn(page: Page, account: Account): Promise<void> {
  await page.addInitScript((token) => localStorage.setItem("mynaksh_token", token), account.token);
}

// Log in through the real form.
export async function logInThroughForm(page: Page, email: string, password = PASSWORD): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Log in" }).click();
}

// Open the chat page and wait until a session is open and its history has loaded.
export async function openChat(page: Page, path = "/chat"): Promise<void> {
  await page.goto(path);
  await page.waitForURL(/\/chat\/[0-9a-f-]{36}$/);
  await expect(page.getByText("Loading chat")).toBeHidden();
}

export function composer(page: Page) {
  return page.getByLabel("Message");
}

// Type a message, send it with Enter, and wait for the assistant's reply to arrive.
export async function sendMessage(page: Page, text: string): Promise<string> {
  const replies = page.getByTestId("message-assistant");
  const before = await replies.count();
  await composer(page).fill(text);
  await composer(page).press("Enter");
  await expect(replies).toHaveCount(before + 1, { timeout: REPLY_TIMEOUT });
  await expect(page.getByTestId("thinking")).toBeHidden();
  return replies.nth(before).innerText();
}

// A link in the top navigation bar. (The memory chip is also a link containing
// the word "Memory", so the bar is named explicitly.)
export function navLink(page: Page, name: "Chat" | "Memory" | "Profile") {
  return page.getByRole("navigation").getByRole("link", { name, exact: true });
}

// The visible "New chat" button. (A chat that has no messages yet is also titled
// "New chat" in the list, and on a phone the hidden sidebar holds a second button.)
export function newChatButton(page: Page) {
  return page.locator("button:visible", { hasText: "New chat" });
}
