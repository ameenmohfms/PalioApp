/**
 * i18n bootstrap. Arabic is the primary locale (spec §3); English secondary.
 * RTL layout is driven by the active locale via isRTL() — consumed by
 * layout components from Phase 2 onward.
 */
import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import ar from "./locales/ar.json";
import en from "./locales/en.json";

export const SUPPORTED_LOCALES = ["ar", "en"] as const;
export type Locale = (typeof SUPPORTED_LOCALES)[number];

export const DEFAULT_LOCALE: Locale = "ar";

export function isRTL(locale: string): boolean {
  return locale.startsWith("ar");
}

export function initI18n(locale: Locale = DEFAULT_LOCALE) {
  if (!i18n.isInitialized) {
    // eslint-disable-next-line import/no-named-as-default-member -- instance API, not the named export
    void i18n.use(initReactI18next).init({
      resources: { ar: { translation: ar }, en: { translation: en } },
      lng: locale,
      fallbackLng: "en",
      interpolation: { escapeValue: false },
    });
  }
  return i18n;
}

export default i18n;
