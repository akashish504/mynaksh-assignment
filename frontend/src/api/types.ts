// The shapes the backend sends and accepts. They mirror the Pydantic models.

export interface TokenResponse {
  access_token: string;
  token_type: "bearer";
  profile_complete: boolean;
}

export interface Zodiac {
  name: string;
  element: string | null;
  traits: string[];
}

export interface Profile {
  name: string | null;
  dob: string | null; // YYYY-MM-DD
  birth_time: string | null; // HH:MM:SS
  birth_time_known: boolean;
  birth_place: string | null;
  language: string;
  profile_updated_via: string | null;
  zodiac: Zodiac | null;
}

export interface Me {
  email: string;
  profile_complete: boolean;
  profile: Profile | null;
}

export interface ProfileUpdate {
  name: string;
  dob: string;
  birth_time: string | null;
  birth_time_known: boolean;
  birth_place: string;
}

export interface Session {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
  type: "answer" | "clarification" | null;
  context_used: string[] | null;
  memory_status: MemoryStatus | null;
}

export interface ChatResponse {
  response: string;
  user_id: string;
  session_id: string;
  message_id: string; // id of the USER message, used for memory polling
  type: "answer" | "clarification";
  options: string[] | null;
  context_used: string[];
}

export type MemoryStatus = "pending" | "done" | "skipped" | "failed";

export interface MemoryUpdate {
  action: "created" | "updated" | "profile_corrected";
  kind: string;
  title: string;
  life_area: string;
  memory_id: string | null;
}

export interface MemoryUpdates {
  status: MemoryStatus;
  updates: MemoryUpdate[];
}

export interface MemoryItem {
  id: string;
  kind: "goal" | "interest" | "preference" | "memory";
  title: string;
  text: string;
  life_area: string;
  attributes: Record<string, string | number>;
  created_at: string;
}

export interface MemoryPage {
  profile: Profile | null;
  memories: Record<string, MemoryItem[]>;
}
