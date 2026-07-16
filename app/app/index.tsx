/**
 * Welcome / capability disclosure / 18+ attestation / language pick
 * (spec §10.1) followed by guest-first onboarding (§10.2): the first
 * conversation starts right after this single screen — nickname only,
 * no account (N9). The attestation gate precedes chat (N7; PLAN C4).
 */
import { useRouter } from "expo-router";
import { useState } from "react";
import {
  ActivityIndicator,
  I18nManager,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { useTranslation } from "react-i18next";

import { ensureGuest } from "../src/api/client";
import { isRTL, type Locale } from "../src/i18n";
import { colors, spacing, type } from "../src/theme/tokens";

export default function Welcome() {
  const { t, i18n } = useTranslation();
  const router = useRouter();
  const [nickname, setNickname] = useState("");
  const [attested, setAttested] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const rtl = isRTL(i18n.language) || I18nManager.isRTL;

  const canStart = attested && nickname.trim().length > 0 && !busy;

  async function start() {
    setBusy(true);
    setError(null);
    try {
      await ensureGuest({
        nickname: nickname.trim(),
        locale: i18n.language.startsWith("ar") ? "ar" : "en",
        attestedAdult: attested,
      });
      router.replace("/chat");
    } catch {
      setError(t("welcome.startError"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.container}>
      <Text style={[styles.title, rtl && styles.rtl]}>{t("welcome.title")}</Text>
      <Text style={[styles.body, rtl && styles.rtl]}>{t("welcome.tagline")}</Text>
      <Text style={[styles.disclosure, rtl && styles.rtl]}>{t("welcome.disclosure")}</Text>

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

      <TextInput
        style={[styles.input, rtl && styles.rtl]}
        placeholder={t("welcome.nicknamePlaceholder")}
        placeholderTextColor={colors.textSecondary}
        value={nickname}
        onChangeText={setNickname}
        maxLength={64}
        accessibilityLabel={t("welcome.nicknamePlaceholder")}
      />

      <Pressable
        style={styles.attestRow}
        accessibilityRole="checkbox"
        accessibilityState={{ checked: attested }}
        onPress={() => setAttested((v) => !v)}
      >
        <View style={[styles.checkbox, attested && styles.checkboxChecked]}>
          {attested && <Text style={styles.checkboxMark}>✓</Text>}
        </View>
        <Text style={[styles.attestText, rtl && styles.rtl]}>
          {t("welcome.adultAttestation")}
        </Text>
      </Pressable>

      {error && <Text style={[styles.error, rtl && styles.rtl]}>{error}</Text>}

      <Pressable
        style={[styles.cta, !canStart && styles.ctaDisabled]}
        accessibilityRole="button"
        disabled={!canStart}
        onPress={start}
      >
        {busy ? (
          <ActivityIndicator color={colors.surface} />
        ) : (
          <Text style={styles.ctaText}>{t("welcome.continue")}</Text>
        )}
      </Pressable>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  container: { padding: spacing.xl, gap: spacing.md, paddingTop: spacing.xl * 2 },
  title: { ...type.title, color: colors.textPrimary },
  body: { ...type.body, color: colors.textSecondary },
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
  input: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 12,
    padding: spacing.md,
    fontSize: 17,
    color: colors.textPrimary,
    backgroundColor: colors.surface,
  },
  attestRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  checkbox: {
    width: 24,
    height: 24,
    borderRadius: 6,
    borderWidth: 2,
    borderColor: colors.accent,
    alignItems: "center",
    justifyContent: "center",
  },
  checkboxChecked: { backgroundColor: colors.accent },
  checkboxMark: { color: colors.surface, fontWeight: "700" },
  attestText: { ...type.body, color: colors.textPrimary, flex: 1 },
  error: { ...type.body, color: colors.crisisText },
  cta: {
    backgroundColor: colors.accent,
    borderRadius: 14,
    padding: spacing.md,
    alignItems: "center",
    marginTop: spacing.sm,
  },
  ctaDisabled: { opacity: 0.45 },
  ctaText: { fontSize: 17, fontWeight: "600", color: colors.surface },
  rtl: { textAlign: "right", writingDirection: "rtl" },
});
