import Alert from "@mui/material/Alert";
import Chip from "@mui/material/Chip";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";
import { useState } from "react";

import { useAuth } from "../auth/useAuth";
import { ProfileForm } from "../components/ProfileForm";
import styles from "./FormPage.module.css";

export function ProfilePage() {
  const { me } = useAuth();
  const [saved, setSaved] = useState(false);
  const zodiac = me?.profile?.zodiac;

  return (
    <div className={styles.centered}>
      <Paper className={styles.card} elevation={2}>
        <Typography variant="h5" component="h1" className={styles.title}>
          Your profile
        </Typography>
        <Typography color="text.secondary" className={styles.subtitle}>
          {me?.email}
        </Typography>

        {zodiac && (
          <div className={styles.zodiac}>
            <Chip color="secondary" label={`${zodiac.name} · ${zodiac.element}`} />
            <Typography variant="body2" color="text.secondary">
              {zodiac.traits.join(", ")}
            </Typography>
          </div>
        )}

        {saved && (
          <Alert severity="success" className={styles.notice}>
            Profile saved.
          </Alert>
        )}
        <ProfileForm
          // The key rebuilds the form with the saved values after each save.
          key={JSON.stringify(me?.profile)}
          initial={me?.profile ?? null}
          submitLabel="Save changes"
          onSaved={() => setSaved(true)}
        />
      </Paper>
    </div>
  );
}
