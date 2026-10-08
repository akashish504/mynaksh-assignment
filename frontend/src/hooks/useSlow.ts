import { useEffect, useState } from "react";

const SLOW_AFTER_MS = 3000;

// True once `waiting` has been true for more than 3 seconds.
// Used to show "Connecting…" when a request is slow (for example while the
// database wakes up after being idle).
export function useSlow(waiting: boolean): boolean {
  const [slow, setSlow] = useState(false);

  useEffect(() => {
    if (!waiting) return;
    const timer = setTimeout(() => setSlow(true), SLOW_AFTER_MS);
    // Runs when the wait ends: cancel the timer and go back to "not slow".
    return () => {
      clearTimeout(timer);
      setSlow(false);
    };
  }, [waiting]);

  return slow;
}
