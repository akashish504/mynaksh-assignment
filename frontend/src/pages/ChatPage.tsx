// The chat window: sessions on the left, the conversation on the right.

import MenuIcon from "@mui/icons-material/Menu";
import SendIcon from "@mui/icons-material/Send";
import Alert from "@mui/material/Alert";
import Drawer from "@mui/material/Drawer";
import IconButton from "@mui/material/IconButton";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useCallback, useEffect, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { api, ApiError } from "../api/client";
import type { MemoryUpdate, Session } from "../api/types";
import { Loading } from "../components/Loading";
import { MemoryChip } from "../components/MemoryChip";
import { SessionList } from "../components/SessionList";
import { useSlow } from "../hooks/useSlow";
import styles from "./ChatPage.module.css";

const MAX_MESSAGE_LENGTH = 2000;
const POLL_INTERVAL_MS = 1000;
const POLL_ATTEMPTS = 8;

// A message as shown on screen.
interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  // What the background memory task stored from this (user) message.
  memoryUpdates?: MemoryUpdate[];
}

interface Conversation {
  sessionId: string;
  messages: ChatMessage[];
}

function wait(milliseconds: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

export function ChatPage() {
  const { sessionId } = useParams();
  const navigate = useNavigate();

  const [sessions, setSessions] = useState<Session[]>([]);
  // False until the list of chats has been fetched for the first time.
  const [sessionsLoaded, setSessionsLoaded] = useState(false);
  // The loaded conversation, tagged with the chat it belongs to. Tagging it means a
  // reply that arrives after the user has switched chats can never land in the wrong one.
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const slow = useSlow(sending);

  const bottomRef = useRef<HTMLDivElement>(null);
  // Stops a second "create a chat" call while the first is still running.
  const creatingRef = useRef(false);

  // What is on screen follows from the address: the open chat's messages once they
  // have loaded, and "loading" until then.
  const isLoaded = conversation !== null && conversation.sessionId === sessionId;
  const messages = isLoaded ? conversation.messages : [];
  const loadingMessages = Boolean(sessionId) && !isLoaded;

  // Change the messages of one specific chat (ignored if that chat is no longer open).
  function updateMessages(forSessionId: string, change: (current: ChatMessage[]) => ChatMessage[]) {
    setConversation((current) =>
      current && current.sessionId === forSessionId
        ? { ...current, messages: change(current.messages) }
        : current,
    );
  }

  const refreshSessions = useCallback(async () => {
    setSessions(await api.listSessions());
  }, []);

  const startNewChat = useCallback(async () => {
    if (creatingRef.current) return;
    creatingRef.current = true;
    try {
      const session = await api.createSession();
      setSessions((current) => [session, ...current]);
      navigate(`/chat/${session.id}`);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not start a new chat.");
    } finally {
      creatingRef.current = false;
    }
  }, [navigate]);

  // On arrival: load the list of chats.
  useEffect(() => {
    api
      .listSessions()
      .then((list) => {
        setSessions(list);
        setSessionsLoaded(true);
      })
      .catch((caught) => setError(caught instanceof ApiError ? caught.message : "Could not load chats."));
  }, []);

  // Whenever no chat is open (first arrival, or an address that was not ours):
  // open the most recent chat, or create the first one.
  useEffect(() => {
    if (!sessionsLoaded || sessionId) return;
    if (sessions.length > 0) {
      navigate(`/chat/${sessions[0].id}`, { replace: true });
    } else {
      // startNewChat only sets state after its request has finished, never during this effect.
      // oxlint-disable-next-line react/set-state-in-effect
      void startNewChat();
    }
  }, [sessionsLoaded, sessionId, sessions, navigate, startNewChat]);

  // Load the messages whenever a different chat is opened.
  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;
    api
      .listMessages(sessionId)
      .then((list) => {
        if (cancelled) return;
        setConversation({
          sessionId,
          messages: list.map((m) => ({ id: m.id, role: m.role, content: m.content })),
        });
      })
      .catch((caught) => {
        if (cancelled) return;
        if (caught instanceof ApiError && caught.status === 404) {
          // Not our chat, or it does not exist: leave this address.
          navigate("/chat", { replace: true });
        } else {
          setError(caught instanceof ApiError ? caught.message : "Could not load this chat.");
        }
      });
    // If the user switches chat before this finishes, ignore the late answer.
    return () => {
      cancelled = true;
    };
  }, [sessionId, navigate]);

  // Keep the newest message in view.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, sending]);

  // Ask once a second, for up to 8 seconds, what the memory task stored.
  async function pollMemoryUpdates(forSessionId: string, messageId: string) {
    for (let attempt = 0; attempt < POLL_ATTEMPTS; attempt++) {
      await wait(POLL_INTERVAL_MS);
      try {
        const result = await api.getMemoryUpdates(messageId);
        if (result.status === "pending") continue;
        if (result.updates.length > 0) {
          updateMessages(forSessionId, (current) =>
            current.map((m) => (m.id === messageId ? { ...m, memoryUpdates: result.updates } : m)),
          );
        }
        return;
      } catch {
        return; // The indicator is a nice-to-have; a failed poll is not shown as an error.
      }
    }
  }

  async function send() {
    const text = draft.trim();
    // Not while the history is still loading or a reply is on its way.
    if (!text || !sessionId || sending || loadingMessages) return;
    const target = sessionId;

    // Show the user's message straight away, under a temporary id.
    const temporaryId = `sending-${Date.now()}`;
    updateMessages(target, (current) => [...current, { id: temporaryId, role: "user", content: text }]);
    setDraft("");
    setError(null);
    setSending(true);

    try {
      const reply = await api.sendMessage(target, text);
      updateMessages(target, (current) => [
        ...current.map((m) => (m.id === temporaryId ? { ...m, id: reply.message_id } : m)),
        { id: `reply-to-${reply.message_id}`, role: "assistant", content: reply.response },
      ]);
      void refreshSessions(); // the title and the order may have changed
      void pollMemoryUpdates(target, reply.message_id);
    } catch (caught) {
      // Put the text back so nothing the user typed is lost.
      updateMessages(target, (current) => current.filter((m) => m.id !== temporaryId));
      setDraft(text);
      setError(caught instanceof ApiError ? caught.message : "Could not send your message.");
    } finally {
      setSending(false);
    }
  }

  function handleKeyDown(event: KeyboardEvent) {
    // Enter sends; Shift+Enter makes a new line.
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void send();
    }
  }

  function openSession(id: string) {
    setDrawerOpen(false);
    setError(null);
    navigate(`/chat/${id}`);
  }

  function handleNewChat() {
    setDrawerOpen(false);
    setError(null);
    void startNewChat();
  }

  const sessionList = (
    <SessionList sessions={sessions} activeId={sessionId} onSelect={openSession} onNew={handleNewChat} />
  );
  // Still getting ready: no session opened yet, or its history is on the way.
  const preparing = !sessionId || loadingMessages;
  const isEmpty = !preparing && messages.length === 0;

  return (
    <div className={styles.layout}>
      {/* Wide screens: the list is always visible. Narrow screens: it opens as a drawer. */}
      <aside className={styles.sidebar}>{sessionList}</aside>
      <Drawer open={drawerOpen} onClose={() => setDrawerOpen(false)}>
        <div className={styles.drawer}>{sessionList}</div>
      </Drawer>

      <section className={styles.conversation}>
        <div className={styles.mobileBar}>
          <IconButton onClick={() => setDrawerOpen(true)} aria-label="Open chats">
            <MenuIcon />
          </IconButton>
          <Typography variant="body2" color="text.secondary">
            Chats
          </Typography>
        </div>

        <div className={styles.messages}>
          {preparing && !error && <Loading label="Loading chat" />}
          {isEmpty && (
            <div className={styles.empty}>
              <Typography variant="h6">Ask me anything</Typography>
              <Typography color="text.secondary">
                Tell me about your goals, or ask what to focus on. I'll remember what matters.
              </Typography>
            </div>
          )}

          {messages.map((message) => (
            <div key={message.id} className={message.role === "user" ? styles.rowUser : styles.rowAssistant}>
              <div
                className={message.role === "user" ? styles.bubbleUser : styles.bubbleAssistant}
                data-testid={`message-${message.role}`}
              >
                {message.content}
              </div>
              {message.memoryUpdates && (
                <div className={styles.chips}>
                  {message.memoryUpdates.map((update, index) => (
                    <MemoryChip key={index} update={update} />
                  ))}
                </div>
              )}
            </div>
          ))}

          {sending && (
            <div className={styles.rowAssistant}>
              <div className={styles.bubbleAssistant} data-testid="thinking">
                <span className={styles.thinking}>{slow ? "Connecting…" : "Thinking…"}</span>
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {error && (
          <Alert severity="error" className={styles.error} onClose={() => setError(null)}>
            {error}
          </Alert>
        )}

        <div className={styles.composer}>
          <TextField
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type your message"
            multiline
            maxRows={5}
            fullWidth
            slotProps={{ htmlInput: { maxLength: MAX_MESSAGE_LENGTH, "aria-label": "Message" } }}
          />
          <IconButton
            color="primary"
            onClick={() => void send()}
            disabled={sending || loadingMessages || !draft.trim() || !sessionId}
            aria-label="Send"
          >
            <SendIcon />
          </IconButton>
        </div>
      </section>
    </div>
  );
}
