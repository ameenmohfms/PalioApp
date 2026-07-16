/**
 * Crisis resources: fetch from the API and cache locally so the crisis
 * screen works offline (spec §10.8). The bundled fallback ships inside the
 * app and is the last resort when nothing was ever fetched.
 *
 * The `verified` flag comes from the server (Hard Rule N8 validation);
 * unverified resources only exist under the dev escape hatch and the UI
 * must show the dev banner for them.
 */
import Constants from "expo-constants";
import AsyncStorageLike from "./crisisCacheStore";

import bundled from "../config/crisis_resources.sa.json";

export type CrisisLine = {
  name: string;
  number: string;
  hours: string;
  language: string;
};

export type CrisisResources = {
  script?: string;
  country: string;
  lines: CrisisLine[];
  verified: boolean;
};

const CACHE_KEY = "palio.crisis.resources.v1";

function apiUrl(): string {
  return (Constants.expoConfig?.extra?.apiUrl as string) ?? "http://localhost:8000";
}

function bundledFallback(): CrisisResources {
  return {
    country: bundled.country,
    lines: bundled.lines as CrisisLine[],
    // Bundled repo config is a blocking placeholder until the operator
    // supplies verified lines — never present it as verified.
    verified: false,
  };
}

export async function getCrisisResources(country = "SA"): Promise<CrisisResources> {
  try {
    const resp = await fetch(`${apiUrl()}/crisis/resources/${country}`);
    if (resp.ok) {
      const data = (await resp.json()) as CrisisResources;
      await AsyncStorageLike.setItem(CACHE_KEY, JSON.stringify(data));
      return data;
    }
  } catch {
    // offline — fall through to cache
  }
  try {
    const cached = await AsyncStorageLike.getItem(CACHE_KEY);
    if (cached) return JSON.parse(cached) as CrisisResources;
  } catch {
    // corrupted cache — fall through to bundled
  }
  return bundledFallback();
}
