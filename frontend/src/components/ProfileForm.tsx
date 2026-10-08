// The birth-details form, used for onboarding and for editing the profile later.

import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import FormControlLabel from "@mui/material/FormControlLabel";
import TextField from "@mui/material/TextField";
import { useState } from "react";
import type { FormEvent } from "react";

import { api, ApiError } from "../api/client";
import type { Profile } from "../api/types";
import { useAuth } from "../auth/useAuth";
import { useSlow } from "../hooks/useSlow";
import styles from "./ProfileForm.module.css";

interface Props {
  initial: Profile | null;
  submitLabel: string;
  onSaved?: () => void;
}

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export function ProfileForm({ initial, submitLabel, onSaved }: Props) {
  const { setMe } = useAuth();
  const [name, setName] = useState(initial?.name ?? "");
  const [dob, setDob] = useState(initial?.dob ?? "");
  // The backend sends HH:MM:SS; a time input works in HH:MM.
  const [birthTime, setBirthTime] = useState(initial?.birth_time?.slice(0, 5) ?? "");
  const [timeUnknown, setTimeUnknown] = useState(initial ? !initial.birth_time_known : false);
  const [birthPlace, setBirthPlace] = useState(initial?.birth_place ?? "");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const slow = useSlow(saving);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSaving(true);
    try {
      const me = await api.saveProfile({
        name,
        dob,
        birth_time: timeUnknown ? null : birthTime,
        birth_time_known: !timeUnknown,
        birth_place: birthPlace,
      });
      setMe(me);
      onSaved?.();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Something went wrong.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className={styles.form}>
      {error && <Alert severity="error">{error}</Alert>}
      <TextField
        label="Name"
        value={name}
        onChange={(event) => setName(event.target.value)}
        required
        fullWidth
      />
      <TextField
        label="Date of birth"
        type="date"
        value={dob}
        onChange={(event) => setDob(event.target.value)}
        slotProps={{ inputLabel: { shrink: true }, htmlInput: { min: "1900-01-01", max: today() } }}
        required
        fullWidth
      />
      <div>
        <TextField
          label="Time of birth"
          type="time"
          value={timeUnknown ? "" : birthTime}
          onChange={(event) => setBirthTime(event.target.value)}
          slotProps={{ inputLabel: { shrink: true } }}
          disabled={timeUnknown}
          required={!timeUnknown}
          fullWidth
        />
        <FormControlLabel
          control={
            <Checkbox
              checked={timeUnknown}
              onChange={(event) => setTimeUnknown(event.target.checked)}
            />
          }
          label="I don't know my birth time"
        />
      </div>
      <TextField
        label="Place of birth"
        value={birthPlace}
        onChange={(event) => setBirthPlace(event.target.value)}
        required
        fullWidth
      />
      <Button type="submit" variant="contained" size="large" disabled={saving}>
        {slow ? "Connecting…" : submitLabel}
      </Button>
    </form>
  );
}
