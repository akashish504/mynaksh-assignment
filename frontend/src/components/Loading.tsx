import CircularProgress from "@mui/material/CircularProgress";
import Typography from "@mui/material/Typography";

import { useSlow } from "../hooks/useSlow";
import styles from "./Loading.module.css";

// A spinner, plus "Connecting…" if the wait passes 3 seconds.
export function Loading({ label }: { label?: string }) {
  const slow = useSlow(true);
  return (
    <div className={styles.loading} role="status">
      <CircularProgress size={22} />
      <Typography variant="body2" color="text.secondary">
        {slow ? "Connecting…" : (label ?? "Loading")}
      </Typography>
    </div>
  );
}
