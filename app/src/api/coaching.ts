/**
 * Coaching API client: the Plan and the strategy lifecycle.
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

export type Strategy = {
  id: string;
  key: string;
  status: string;
  feedback: string | null;
  outcome: string | null;
  title: string;
  summary: string;
  steps: string[];
  try_this_week: string;
  adapt_if: string[];
};

export type LibraryEntry = { key: string; category: string; title: string; summary: string };

export type Plan = {
  strategies: Strategy[];
  library: LibraryEntry[];
  plan_summary: string | null;
};

export async function fetchPlan(): Promise<Plan> {
  const resp = await authed("/coaching/plan");
  if (!resp.ok) throw new Error(`plan failed: ${resp.status}`);
  return (await resp.json()) as Plan;
}

export async function assignStrategy(key: string): Promise<Strategy> {
  const resp = await authed("/coaching/assign", {
    method: "POST",
    body: JSON.stringify({ strategy_key: key }),
  });
  if (!resp.ok) throw new Error(`assign failed: ${resp.status}`);
  return (await resp.json()) as Strategy;
}

export async function rateStrategy(
  id: string,
  feedback: "helped" | "did_not_help" | "partial",
  outcome?: string,
): Promise<Strategy> {
  const resp = await authed(`/coaching/strategies/${id}/feedback`, {
    method: "POST",
    body: JSON.stringify({ feedback, outcome }),
  });
  if (!resp.ok) throw new Error(`feedback failed: ${resp.status}`);
  return (await resp.json()) as Strategy;
}

export async function adaptStrategy(id: string): Promise<Strategy> {
  const resp = await authed(`/coaching/strategies/${id}/adapt`, { method: "POST" });
  if (!resp.ok) throw new Error(`adapt failed: ${resp.status}`);
  return (await resp.json()) as Strategy;
}

export async function dropStrategy(id: string): Promise<Strategy> {
  const resp = await authed(`/coaching/strategies/${id}/drop`, { method: "POST" });
  if (!resp.ok) throw new Error(`drop failed: ${resp.status}`);
  return (await resp.json()) as Strategy;
}

export async function reactToMessage(
  messageId: string,
  feedback: "helped" | "did_not_help",
): Promise<void> {
  await authed(`/coaching/messages/${messageId}/reaction`, {
    method: "POST",
    body: JSON.stringify({ feedback }),
  });
}
