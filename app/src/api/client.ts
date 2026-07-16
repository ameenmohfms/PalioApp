/**
 * Typed API client. Guest-first: the device keeps a stable guest ID in
 * SecureStore; the JWT arrives from /auth/guest and is stored alongside it.
 */
import Constants from "expo-constants";
import * as SecureStore from "expo-secure-store";

const TOKEN_KEY = "palio.auth.token";
const GUEST_ID_KEY = "palio.guest.id";

export function apiUrl(): string {
  return (Constants.expoConfig?.extra?.apiUrl as string) ?? "http://localhost:8000";
}

export async function getToken(): Promise<string | null> {
  return SecureStore.getItemAsync(TOKEN_KEY);
}

async function authedFetch(path: string, init?: RequestInit): Promise<Response> {
  const token = await getToken();
  return fetch(`${apiUrl()}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init?.headers ?? {}),
    },
  });
}

function randomHex(bytes: number): string {
  let out = "";
  for (let i = 0; i < bytes; i++) {
    out += Math.floor(Math.random() * 256)
      .toString(16)
      .padStart(2, "0");
  }
  return out;
}

export async function ensureGuest(params: {
  nickname: string;
  locale: "ar" | "en";
  attestedAdult: boolean;
}): Promise<{ userId: string; nickname: string }> {
  let guestId = await SecureStore.getItemAsync(GUEST_ID_KEY);
  if (!guestId) {
    guestId = randomHex(16);
    await SecureStore.setItemAsync(GUEST_ID_KEY, guestId);
  }
  const resp = await fetch(`${apiUrl()}/auth/guest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      device_guest_id: guestId,
      nickname: params.nickname,
      locale: params.locale,
      attested_adult: params.attestedAdult,
    }),
  });
  if (!resp.ok) throw new Error(`guest auth failed: ${resp.status}`);
  const data = await resp.json();
  await SecureStore.setItemAsync(TOKEN_KEY, data.token);
  return { userId: data.user_id, nickname: data.nickname };
}

export type TurnResponse = {
  reply: string;
  risk_level: string;
  ui_action: string | null;
  crisis: { lines: unknown[]; verified: boolean; country: string } | null;
};

export async function createSession(): Promise<string> {
  const resp = await authedFetch("/chat/sessions", { method: "POST" });
  if (!resp.ok) throw new Error(`create session failed: ${resp.status}`);
  return (await resp.json()).id as string;
}

export async function sendMessage(sessionId: string, content: string): Promise<TurnResponse> {
  const resp = await authedFetch(`/chat/sessions/${sessionId}/messages`, {
    method: "POST",
    body: JSON.stringify({ content }),
  });
  if (!resp.ok) throw new Error(`send failed: ${resp.status}`);
  return (await resp.json()) as TurnResponse;
}

export type HistoryItem = { id: string; role: string; content: string; created_at: string };

export async function fetchHistory(sessionId: string): Promise<HistoryItem[]> {
  const resp = await authedFetch(`/chat/sessions/${sessionId}/messages`);
  if (!resp.ok) throw new Error(`history failed: ${resp.status}`);
  return (await resp.json()) as HistoryItem[];
}
