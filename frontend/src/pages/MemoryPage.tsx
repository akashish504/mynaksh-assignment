// "What I remember about you": the profile summary and the stored memories, with delete.

import DeleteOutlineIcon from "@mui/icons-material/DeleteOutlined";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import IconButton from "@mui/material/IconButton";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";
import { useEffect, useState } from "react";

import { api, ApiError } from "../api/client";
import type { MemoryItem, MemoryPage as MemoryPageData } from "../api/types";
import { Loading } from "../components/Loading";
import styles from "./MemoryPage.module.css";

function capitalize(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

export function MemoryPage() {
  const [page, setPage] = useState<MemoryPageData | null>(null);
  const [error, setError] = useState<string | null>(null);
  // The memory the user has asked to delete, while the confirmation is open.
  const [toDelete, setToDelete] = useState<MemoryItem | null>(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    api
      .getMemoryPage()
      .then(setPage)
      .catch((caught) => setError(caught instanceof ApiError ? caught.message : "Could not load your memories."));
  }, []);

  async function confirmDelete() {
    if (!toDelete || !page) return;
    setDeleting(true);
    try {
      await api.deleteMemory(toDelete.id);
      // Remove it from the screen, and drop the life area if it is now empty.
      const memories: Record<string, MemoryItem[]> = {};
      for (const [area, items] of Object.entries(page.memories)) {
        const remaining = items.filter((item) => item.id !== toDelete.id);
        if (remaining.length > 0) memories[area] = remaining;
      }
      setPage({ ...page, memories });
      setToDelete(null);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not delete this memory.");
      setToDelete(null);
    } finally {
      setDeleting(false);
    }
  }

  if (error && !page) {
    return (
      <div className={styles.page}>
        <Alert severity="error">{error}</Alert>
      </div>
    );
  }
  if (!page) {
    return <Loading label="Loading your memories" />;
  }

  const profile = page.profile;
  const areas = Object.keys(page.memories).sort();

  return (
    <div className={styles.page}>
      <Typography variant="h5" component="h1" className={styles.title}>
        What I remember about you
      </Typography>
      {error && (
        <Alert severity="error" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {profile && (
        <Paper className={styles.card} elevation={1}>
          <Typography variant="overline" color="text.secondary">
            Profile
          </Typography>
          <dl className={styles.facts}>
            <dt>Name</dt>
            <dd>{profile.name ?? "Not known yet"}</dd>
            <dt>Date of birth</dt>
            <dd>{profile.dob ? formatDate(profile.dob) : "Not known yet"}</dd>
            <dt>Birth time</dt>
            <dd>{profile.birth_time_known && profile.birth_time ? profile.birth_time.slice(0, 5) : "Unknown"}</dd>
            <dt>Birth place</dt>
            <dd>{profile.birth_place ?? "Not known yet"}</dd>
            <dt>Sun sign</dt>
            <dd>{profile.zodiac ? `${profile.zodiac.name} (${profile.zodiac.element})` : "Not known yet"}</dd>
          </dl>
        </Paper>
      )}

      {areas.length === 0 && (
        <Paper className={styles.card} elevation={1}>
          <Typography>Nothing stored yet.</Typography>
          <Typography color="text.secondary">
            As you chat, I'll keep the goals, preferences and life events worth remembering here.
          </Typography>
        </Paper>
      )}

      {areas.map((area) => (
        <section key={area}>
          <Typography variant="h6" component="h2" className={styles.area}>
            {capitalize(area)}
          </Typography>
          <div className={styles.list}>
            {page.memories[area].map((memory) => (
              <Paper key={memory.id} className={styles.memory} elevation={1}>
                <div className={styles.memoryBody}>
                  <div className={styles.memoryMeta}>
                    <Chip size="small" label={capitalize(memory.kind)} />
                    <Typography variant="caption" color="text.secondary">
                      Saved {formatDate(memory.created_at)}
                    </Typography>
                  </div>
                  <Typography>{memory.text}</Typography>
                </div>
                <IconButton onClick={() => setToDelete(memory)} aria-label={`Delete memory: ${memory.title}`}>
                  <DeleteOutlineIcon />
                </IconButton>
              </Paper>
            ))}
          </div>
        </section>
      ))}

      <Dialog open={toDelete !== null} onClose={() => setToDelete(null)}>
        <DialogTitle>Delete this memory?</DialogTitle>
        <DialogContent>
          <Typography>{toDelete?.text}</Typography>
          <Typography variant="body2" color="text.secondary" className={styles.dialogNote}>
            I'll stop using it in my answers. This cannot be undone.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setToDelete(null)}>Cancel</Button>
          <Button color="error" variant="contained" onClick={() => void confirmDelete()} disabled={deleting}>
            Delete
          </Button>
        </DialogActions>
      </Dialog>
    </div>
  );
}
