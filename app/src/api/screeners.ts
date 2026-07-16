/**
 * Screening API client (spec §7). Item text comes verbatim from the
 * server-side versioned instrument definition (Hard Rule A3) — the app
 * renders it untouched in fixed cards.
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

export type ScaleOption = { value: number; label: string };
export type InstrumentItem = { id: number; text: string; part?: string };
export type Instrument = {
  id: string;
  key: string;
  version: string;
  language: string;
  title: string;
  definition: {
    title: string;
    instructions: string;
    scale: ScaleOption[];
    items: InstrumentItem[];
  };
};

export type Formulation = {
  reported_summary: string;
  score_meaning: string;
  honest_line: string;
  options: string[];
  rescreen_days: number;
  scores: Record<string, number>;
  band_key: string;
  alerts: string[];
  ui_action: string | null;
};

export async function listInstruments(): Promise<Instrument[]> {
  const resp = await authed("/screeners");
  if (!resp.ok) throw new Error(`list failed: ${resp.status}`);
  return (await resp.json()) as Instrument[];
}

export async function startScreening(instrumentId: string): Promise<string> {
  const resp = await authed("/screeners/start", {
    method: "POST",
    body: JSON.stringify({ instrument_id: instrumentId, consent: true }),
  });
  if (!resp.ok) throw new Error(`start failed: ${resp.status}`);
  return (await resp.json()).id as string;
}

export async function answerItem(
  resultId: string,
  itemId: number,
  value: number,
): Promise<void> {
  const resp = await authed(`/screeners/results/${resultId}/answer`, {
    method: "POST",
    body: JSON.stringify({ item_id: itemId, value }),
  });
  if (!resp.ok) throw new Error(`answer failed: ${resp.status}`);
}

export async function completeScreening(resultId: string): Promise<Formulation> {
  const resp = await authed(`/screeners/results/${resultId}/complete`, { method: "POST" });
  if (!resp.ok) throw new Error(`complete failed: ${resp.status}`);
  return (await resp.json()) as Formulation;
}
