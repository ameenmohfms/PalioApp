import { Stack, usePathname, useRouter } from "expo-router";
import { getLocales } from "expo-localization";
import { StatusBar } from "expo-status-bar";
import { Pressable, StyleSheet, Text } from "react-native";
import { useTranslation } from "react-i18next";

import { DEFAULT_LOCALE, initI18n, SUPPORTED_LOCALES, type Locale } from "../src/i18n";
import { colors, spacing } from "../src/theme/tokens";

const deviceLang = getLocales()[0]?.languageCode ?? DEFAULT_LOCALE;
const startLocale: Locale = (SUPPORTED_LOCALES as readonly string[]).includes(deviceLang)
  ? (deviceLang as Locale)
  : DEFAULT_LOCALE;

initI18n(startLocale);

/**
 * Persistent, quiet help affordance (spec §10.8): reachable from every
 * screen, calm wording, no alarm styling. Hidden on the crisis screen
 * itself.
 */
function HelpAffordance() {
  const router = useRouter();
  const pathname = usePathname();
  const { t } = useTranslation();

  if (pathname === "/crisis") return null;
  return (
    <Pressable
      style={styles.help}
      accessibilityRole="button"
      accessibilityLabel={t("crisis.helpAffordanceLabel")}
      onPress={() => router.push("/crisis")}
    >
      <Text style={styles.helpText}>{t("crisis.helpAffordance")}</Text>
    </Pressable>
  );
}

export default function RootLayout() {
  return (
    <>
      <StatusBar style="auto" />
      <Stack screenOptions={{ headerShown: false }} />
      <HelpAffordance />
    </>
  );
}

const styles = StyleSheet.create({
  help: {
    position: "absolute",
    bottom: spacing.lg,
    right: spacing.lg,
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: 20,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
  },
  helpText: { fontSize: 14, color: colors.textSecondary },
});
