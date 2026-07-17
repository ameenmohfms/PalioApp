/**
 * Patterns map API client (spec §8): suggestion queue + user controls.
 */
import Constants from "expo-constants";

import { getToken } from "./client";

function apiUrl(): string {
  return (Constants.expoConfig?.extra?.apiUrl as string) ?? "http://localhost:8000";
}

async function authed(path: string, init?: RequestInit): Promise<Response> {
  const token = await getToken();
  return fetch(`${apiUrl()}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });
}

export type PatternNode = {
  id: string;
  type: "trigger" | "strength" | "context" | "strategy_outcome" | "win";
  text: string;
  status: string;
  confidence: number;
  evidence_count: number;
  created_at: string;
};

export type PatternsListing = { proposed: PatternNode[]; confirmed: PatternNode[] };

export async function listPatterns(): Promise<PatternsListing> {
  const resp = await authed("/patterns");
  if (!resp.ok) throw new Error(`patterns failed: ${resp.status}`);
  return (await resp.json()) as PatternsListing;
}

export async function confirmPattern(id: string): Promise<void> {
  await authed(`/patterns/${id}/confirm`, { method: "POST" });
}

export async function rejectPattern(id: string): Promise<void> {
  await authed(`/patterns/${id}/reject`, { method: "POST" });
}

export async function editPattern(id: string, text: string): Promise<void> {
  await authed(`/patterns/${id}`, { method: "PATCH", body: JSON.stringify({ text }) });
}

export async function deletePattern(id: string): Promise<void> {
  await authed(`/patterns/${id}`, { method: "DELETE" });
}

export async function setSessionMemory(sessionId: string, paused: boolean): Promise<void> {
  await authed(`/chat/sessions/${sessionId}/memory`, {
    method: "PATCH",
    body: JSON.stringify({ paused }),
  });
}

export async function endSession(sessionId: string): Promise<void> {
  await authed(`/chat/sessions/${sessionId}/end`, { method: "POST" });
}

export type ScreenerHistoryItem = {
  id: string;
  instrument_key: string;
  scores: Record<string, number>;
  band: string;
  taken_at: string | null;
  completed: boolean;
};

export async function screenerHistory(): Promise<ScreenerHistoryItem[]> {
  const resp = await authed("/screeners/results");
  if (!resp.ok) throw new Error(`history failed: ${resp.status}`);
  return (await resp.json()) as ScreenerHistoryItem[];
}
