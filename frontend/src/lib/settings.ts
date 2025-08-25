//src/lib/settings.ts
import { API_BASE } from "../components/api";

export type ServerSettings = { MAX_FILES: number; MAX_BYTES: number };

export async function fetchServerSettings(): Promise<ServerSettings> {
  const res = await fetch(`${API_BASE}/server-settings`, { cache: "no-store" });
  const json = await res.json();
  return {
    MAX_FILES: Number(json.MAX_FILES ?? 0),
    MAX_BYTES: Number(json.MAX_BYTES ?? 0),
  };
}