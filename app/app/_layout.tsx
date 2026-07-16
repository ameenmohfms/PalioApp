import { Stack } from "expo-router";
import { getLocales } from "expo-localization";
import { StatusBar } from "expo-status-bar";

import { DEFAULT_LOCALE, initI18n, SUPPORTED_LOCALES, type Locale } from "../src/i18n";

const deviceLang = getLocales()[0]?.languageCode ?? DEFAULT_LOCALE;
const startLocale: Locale = (SUPPORTED_LOCALES as readonly string[]).includes(deviceLang)
  ? (deviceLang as Locale)
  : DEFAULT_LOCALE;

initI18n(startLocale);

export default function RootLayout() {
  return (
    <>
      <StatusBar style="auto" />
      <Stack screenOptions={{ headerShown: false }} />
    </>
  );
}
