/**
 * Settings (spec §10.9): language, capability disclosure (A4, permanently
 * visible here), export data, delete account (hard delete + confirmation).
 */
import { useRouter } from "expo-router";
import { useState } from "react";
import {
  Alert,
  I18nManager,
  Pressable,
  ScrollView,
  Share,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { useTranslation } from "react-i18next";

import { deleteAccount, exportAccount } from "../src/api/care";
import { isRTL, type Locale } from "../src/i18n";
import { colors, spacing, type } from "../src/theme/tokens";

export default function Settings() {
  const { t, i18n } = useTranslation();
  const router = useRouter();
  const rtl = isRTL(i18n.language) || I18nManager.isRTL;
  const [busy, setBusy] = useState(false);

  async function onExport() {
    setBusy(true);
    try {
      const data = await exportAccount();
      await Share.share({ message: JSON.stringify(data, null, 2) });
    } finally {
      setBusy(false);
    }
  }

  function onDelete() {
    Alert.alert(t("settings.deleteTitle"), t("settings.deleteConfirm"), [
      { text: t("settings.cancel"), style: "cancel" },
      {
        text: t("settings.deleteDo"),
        style: "destructive",
        onPress: async () => {
          await deleteAccount();
          router.replace("/");
        },
      },
    ]);
  }

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.container}>
      <Text style={[styles.title, rtl && styles.rtl]}>{t("settings.title")}</Text>

      <Text style={[styles.disclosure, rtl && styles.rtl]}>{t("welcome.disclosure")}</Text>

      <Text style={[styles.section, rtl && styles.rtl]}>{t("welcome.languageLabel")}</Text>
      <View style={styles.langRow}>
        {(["ar", "en"] as Locale[]).map((lng) => (
          <Pressable
            key={lng}
            style={[styles.langChip, i18n.language.startsWith(lng) && styles.langChipActive]}
            accessibilityRole="button"
            onPress={() => i18n.changeLanguage(lng)}
          >
            <Text
              style={[
                styles.langChipText,
                i18n.language.startsWith(lng) && styles.langChipTextActive,
              ]}
            >
              {lng === "ar" ? "العربية" : "English"}
            </Text>
          </Pressable>
        ))}
      </View>

      <Pressable
        style={[styles.row, busy && { opacity: 0.5 }]}
        accessibilityRole="button"
        disabled={busy}
        onPress={onExport}
      >
        <Text style={[styles.body, rtl && styles.rtl]}>{t("settings.export")}</Text>
      </Pressable>

      <Pressable style={styles.rowDanger} accessibilityRole="button" onPress={onDelete}>
        <Text style={[styles.dangerText, rtl && styles.rtl]}>{t("settings.deleteTitle")}</Text>
      </Pressable>
      <Text style={[styles.meta, rtl && styles.rtl]}>{t("settings.deleteNote")}</Text>
      <View style={{ height: spacing.xl }} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  container: { padding: spacing.xl, gap: spacing.md, paddingTop: spacing.xl * 1.5 },
  title: { ...type.title, color: colors.textPrimary },
  section: { fontSize: 16, fontWeight: "600", color: colors.textPrimary },
  body: { ...type.body, color: colors.textPrimary },
  meta: { fontSize: 13, lineHeight: 19, color: colors.textSecondary },
  disclosure: {
    ...type.body,
    color: colors.textPrimary,
    backgroundColor: colors.accentSoft,
    borderRadius: 12,
    padding: spacing.md,
  },
  langRow: { flexDirection: "row", gap: spacing.sm },
  langChip: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 18,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
  },
  langChipActive: { backgroundColor: colors.accent, borderColor: colors.accent },
  langChipText: { fontSize: 15, color: colors.textPrimary },
  langChipTextActive: { color: colors.surface },
  row: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 12,
    padding: spacing.md,
  },
  rowDanger: {
    backgroundColor: colors.crisisSurface,
    borderWidth: 1,
    borderColor: colors.crisisText,
    borderRadius: 12,
    padding: spacing.md,
  },
  dangerText: { ...type.body, color: colors.crisisText, fontWeight: "600" },
  rtl: { textAlign: "right", writingDirection: "rtl" },
});
