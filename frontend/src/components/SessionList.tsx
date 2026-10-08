// The list of chat windows, with a "New chat" button.

import AddIcon from "@mui/icons-material/Add";
import Button from "@mui/material/Button";
import List from "@mui/material/List";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemText from "@mui/material/ListItemText";

import type { Session } from "../api/types";
import styles from "./SessionList.module.css";

interface Props {
  sessions: Session[];
  activeId: string | undefined;
  onSelect: (sessionId: string) => void;
  onNew: () => void;
}

export function SessionList({ sessions, activeId, onSelect, onNew }: Props) {
  return (
    <div className={styles.container}>
      <Button variant="contained" startIcon={<AddIcon />} onClick={onNew} fullWidth>
        New chat
      </Button>
      <List className={styles.list} dense>
        {sessions.map((session) => (
          <ListItemButton
            key={session.id}
            selected={session.id === activeId}
            onClick={() => onSelect(session.id)}
            className={styles.item}
          >
            <ListItemText primary={session.title} slotProps={{ primary: { noWrap: true } }} />
          </ListItemButton>
        ))}
      </List>
    </div>
  );
}
