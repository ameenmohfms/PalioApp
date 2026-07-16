/**
 * Phase 0 placeholder for the Welcome / capability-disclosure screen.
 * Phase 2 replaces this with the full disclosure + 18+ attestation +
 * language pick flow (spec §10.1). The disclosure copy is already the
 * real A4 text so it is never an afterthought.
 */
import { useTranslation } from "react-i18next";
import { I18nManager, StyleSheet, Text, View } from "react-native";

import { isRTL } from "../src/i18n";
import { colors, spacing, type } from "../src/theme/tokens";

export default function Welcome() {
  const { t, i18n } = useTranslation();
  const rtl = isRTL(i18n.language) || I18nManager.isRTL;

  return (
    <View style={styles.container}>
      <Text style={[styles.title, rtl && styles.rtl]}>{t("welcome.title")}</Text>
      <Text style={[styles.body, rtl && styles.rtl]}>{t("welcome.tagline")}</Text>
      <Text style={[styles.disclosure, rtl && styles.rtl]}>{t("welcome.disclosure")}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
    justifyContent: "center",
    padding: spacing.xl,
    gap: spacing.md,
  },
  title: { ...type.title, color: colors.textPrimary },
  body: { ...type.body, color: colors.textSecondary },
  disclosure: {
    ...type.body,
    color: colors.textPrimary,
    backgroundColor: colors.accentSoft,
    borderRadius: 12,
    padding: spacing.md,
  },
  rtl: { textAlign: "right", writingDirection: "rtl" },
});
