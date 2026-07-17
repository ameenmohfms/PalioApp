/**
 * Bridge-to-care API client: reports, referrals, account rights.
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

export type Referral = {
  id: string;
  name: string;
  type: string;
  city: string;
  languages: string[];
  contact: string;
  telehealth: boolean;
};

export async function listReferrals(city?: string): Promise<Referral[]> {
  const query = city ? `?city=${encodeURIComponent(city)}` : "";
  const resp = await authed(`/referrals${query}`);
  if (!resp.ok) throw new Error(`referrals failed: ${resp.status}`);
  return (await resp.json()) as Referral[];
}

export async function tapReferral(id: string): Promise<void> {
  await authed(`/referrals/${id}/tap`, { method: "POST" });
}

export async function setCity(city: string): Promise<void> {
  await authed("/account/city", { method: "PATCH", body: JSON.stringify({ city }) });
}

export async function generateReport(params: {
  language: "ar" | "en";
  userMedications?: string;
}): Promise<{ id: string; downloadUrl: string }> {
  const resp = await authed("/reports", {
    method: "POST",
    body: JSON.stringify({
      language: params.language,
      user_medications: params.userMedications || null,
      consent_share: true,
    }),
  });
  if (!resp.ok) throw new Error(`report failed: ${resp.status}`);
  const data = await resp.json();
  return { id: data.id, downloadUrl: `${apiUrl()}/reports/${data.id}/download` };
}

export async function exportAccount(): Promise<unknown> {
  const resp = await authed("/account/export");
  if (!resp.ok) throw new Error(`export failed: ${resp.status}`);
  return resp.json();
}

export async function deleteAccount(): Promise<void> {
  const resp = await authed("/account", { method: "DELETE" });
  if (!resp.ok) throw new Error(`delete failed: ${resp.status}`);
}
