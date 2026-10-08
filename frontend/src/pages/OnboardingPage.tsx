import Button from "@mui/material/Button";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";

import { useAuth } from "../auth/useAuth";
import { ProfileForm } from "../components/ProfileForm";
import styles from "./FormPage.module.css";

// Shown once after signup. Saving it marks the profile complete, and the
// route guards then let the user through to chat.
export function OnboardingPage() {
  const { me, logout } = useAuth();

  return (
    <div className={styles.centered}>
      <Paper className={styles.card} elevation={2}>
        <Typography variant="h5" component="h1" className={styles.title}>
          Your birth details
        </Typography>
        <Typography color="text.secondary" className={styles.subtitle}>
          These let us personalise your guidance. We work out your sun sign from your date of birth.
        </Typography>
        <ProfileForm initial={me?.profile ?? null} submitLabel="Continue" />
        <Button onClick={logout} className={styles.secondaryAction}>
          Log out
        </Button>
      </Paper>
    </div>
  );
}
