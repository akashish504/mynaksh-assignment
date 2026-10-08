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

function wait(milliseconds: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

export function ChatPage() {
  const { sessionId } = useParams();
  const navigate = useNavigate();

  const [sessions, setSessions] = useState<Session[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const slow = useSlow(sending);

  const bottomRef = useRef<HTMLDivElement>(null);
  // Stops a second "create first session" call (React runs effects twice in development).
  const startedRef = useRef(false);

  const refreshSessions = useCallback(async () => {
    const list = await api.listSessions();
    setSessions(list);
    return list;
  }, []);

  const startNewChat = useCallback(async () => {
    setDrawerOpen(false);
    try {
      const session = await api.createSession();
      setSessions((current) => [session, ...current]);
      navigate(`/chat/${session.id}`);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not start a new chat.");
    }
  }, [navigate]);

  // On arrival: load the sessions, then open the most recent one (or create the first).
  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;
    refreshSessions()
      .then((list) => {
        if (sessionId) return;
        if (list.length > 0) {
          navigate(`/chat/${list[0].id}`, { replace: true });
        } else {
          void startNewChat();
        }
      })
      .catch((caught) => setError(caught instanceof ApiError ? caught.message : "Could not load chats."));
    // Runs once on arrival only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Load the messages whenever a different session is opened.
  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;
    setMessages([]);
    setError(null);
    setLoadingMessages(true);
    api
      .listMessages(sessionId)
      .then((list) => {
        if (cancelled) return;
        setMessages(list.map((m) => ({ id: m.id, role: m.role, content: m.content })));
      })
      .catch((caught) => {
        if (cancelled) return;
        if (caught instanceof ApiError && caught.status === 404) {
          navigate("/chat", { replace: true });
        } else {
          setError(caught instanceof ApiError ? caught.message : "Could not load this chat.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingMessages(false);
      });
    // If the user switches session before this finishes, ignore the late answer.
    return () => {
      cancelled = true;
    };
  }, [sessionId, navigate]);

  // Keep the newest message in view.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, sending]);

  // Ask once a second, for up to 8 seconds, what the memory task stored.
  async function pollMemoryUpdates(messageId: string) {
    for (let attempt = 0; attempt < POLL_ATTEMPTS; attempt++) {
      await wait(POLL_INTERVAL_MS);
      try {
        const result = await api.getMemoryUpdates(messageId);
        if (result.status === "pending") continue;
        if (result.updates.length > 0) {
          setMessages((current) =>
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
    if (!text || !sessionId || sending) return;

    // Show the user's message straight away, under a temporary id.
    const temporaryId = `sending-${Date.now()}`;
    setMessages((current) => [...current, { id: temporaryId, role: "user", content: text }]);
    setDraft("");
    setError(null);
    setSending(true);

    try {
      const reply = await api.sendMessage(sessionId, text);
      setMessages((current) => [
        ...current.map((m) => (m.id === temporaryId ? { ...m, id: reply.message_id } : m)),
        { id: `reply-to-${reply.message_id}`, role: "assistant", content: reply.response },
      ]);
      void refreshSessions(); // the title and the order may have changed
      void pollMemoryUpdates(reply.message_id);
    } catch (caught) {
      // Put the text back so nothing the user typed is lost.
      setMessages((current) => current.filter((m) => m.id !== temporaryId));
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
    navigate(`/chat/${id}`);
  }

  const sessionList = (
    <SessionList sessions={sessions} activeId={sessionId} onSelect={openSession} onNew={startNewChat} />
  );
  const isEmpty = !loadingMessages && messages.length === 0;

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
          {loadingMessages && <Loading label="Loading chat" />}
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
              <div className={message.role === "user" ? styles.bubbleUser : styles.bubbleAssistant}>
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
              <div className={styles.bubbleAssistant}>
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
            disabled={sending || !draft.trim() || !sessionId}
            aria-label="Send"
          >
            <SendIcon />
          </IconButton>
        </div>
      </section>
    </div>
  );
}
