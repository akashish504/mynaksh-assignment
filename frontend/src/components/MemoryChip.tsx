// The "memory updated" indicator shown under a user message.

import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import Chip from "@mui/material/Chip";
import { Link } from "react-router-dom";

import type { MemoryUpdate } from "../api/types";

function capitalize(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

// e.g. "Memory updated: Career goal · Switch jobs"
function describeUpdate(update: MemoryUpdate): string {
  if (update.action === "profile_corrected") {
    return `Profile updated: ${update.title}`;
  }
  return `Memory updated: ${capitalize(update.life_area)} ${update.kind} · ${update.title}`;
}

export function MemoryChip({ update }: { update: MemoryUpdate }) {
  const target = update.action === "profile_corrected" ? "/profile" : "/memory";
  return (
    <Chip
      component={Link}
      to={target}
      clickable
      size="small"
      color="secondary"
      variant="outlined"
      icon={<AutoAwesomeIcon />}
      label={describeUpdate(update)}
    />
  );
}
