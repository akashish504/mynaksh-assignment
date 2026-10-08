// Login and signup share one form; only the wording and the API call differ.

import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Paper from "@mui/material/Paper";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";

import { ApiError } from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useSlow } from "../hooks/useSlow";
import styles from "./AuthPage.module.css";

const MIN_PASSWORD_LENGTH = 8;

export function AuthPage({ mode }: { mode: "login" | "signup" }) {
  const { login, signup } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const slow = useSlow(submitting);
  const isSignup = mode === "signup";

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      // On success the route guards move the user on to onboarding or chat.
      await (isSignup ? signup(email, password) : login(email, password));
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Something went wrong.");
      setSubmitting(false);
    }
  }

  return (
    <div className={styles.page}>
      <Paper className={styles.card} elevation={2}>
        <Typography variant="h4" component="h1" className={styles.brand}>
          MyNaksh
        </Typography>
        <Typography color="text.secondary" className={styles.subtitle}>
          {isSignup ? "Create your account" : "Welcome back"}
        </Typography>

        <form onSubmit={handleSubmit} className={styles.form}>
          {error && <Alert severity="error">{error}</Alert>}
          <TextField
            label="Email"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            autoComplete="email"
            required
            fullWidth
          />
          <TextField
            label="Password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete={isSignup ? "new-password" : "current-password"}
            helperText={isSignup ? `At least ${MIN_PASSWORD_LENGTH} characters` : undefined}
            slotProps={{ htmlInput: { minLength: isSignup ? MIN_PASSWORD_LENGTH : undefined } }}
            required
            fullWidth
          />
          <Button type="submit" variant="contained" size="large" disabled={submitting}>
            {slow ? "Connecting…" : isSignup ? "Sign up" : "Log in"}
          </Button>
        </form>

        <Typography variant="body2" className={styles.switch}>
          {isSignup ? "Already have an account? " : "New here? "}
          <Link to={isSignup ? "/login" : "/signup"}>{isSignup ? "Log in" : "Create an account"}</Link>
        </Typography>
      </Paper>
    </div>
  );
}
