import { API_URL } from "./helpers";

// Fail early, with a clear message, if the backend is not running.
export default async function globalSetup() {
  try {
    const response = await fetch(`${API_URL}/health`);
    if (!response.ok) throw new Error(`/health answered ${response.status}`);
  } catch (error) {
    throw new Error(
      `The backend is not reachable at ${API_URL} (${error}).\n` +
        "Start it from the repository root with:\n" +
        "  docker compose -f docker-compose.dev.yml up -d --build",
    );
  }
}
