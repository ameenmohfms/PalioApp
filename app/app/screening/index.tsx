/**
 * Screening list (spec §10.4). Consent framing is explicit before start:
 * a screening, not a diagnosis. Arabic instruments appear only after the
 * operator supplies clinically verified translations (§16 #2).
 */
import { useRouter } from "expo-router";
import { useEffect, useState } from "react";
import { I18nManager, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useTranslation } from "react-i18next";

import { listInstruments, type Instrument } from "../../src/api/screeners";
import { isRTL } from "../../src/i18n";
import { colors, spacing, type } from "../../src/theme/tokens";

export default function ScreeningList() {
  const { t, i18n } = useTranslation();
  const router = useRouter();
  const rtl = isRTL(i18n.language) || I18nManager.isRTL;
  const [instruments, setInstruments] = useState<Instrument[] | null>(null);

  useEffect(() => {
    let mounted = true;
    listInstruments()
      .then((list) => mounted && setInstruments(list))
      .catch(() => mounted && setInstruments([]));
    return () => {
      mounted = false;
    };
  }, []);

  const arPending = i18n.language.startsWith("ar");

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.container}>
      <Text style={[styles.title, rtl && styles.rtl]}>{t("screening.title")}</Text>
      <Text style={[styles.consent, rtl && styles.rtl]}>{t("screening.consentNote")}</Text>
      {arPending && (
        <Text style={[styles.arPending, rtl && styles.rtl]}>{t("screening.arPending")}</Text>
      )}
      {(instruments ?? []).map((inst) => (
        <Pressable
          key={inst.id}
          style={styles.card}
          accessibilityRole="button"
          onPress={() => router.push({ pathname: "/screening/[id]", params: { id: inst.id } })}
        >
          <Text style={styles.cardTitle}>{inst.title}</Text>
          <Text style={styles.cardMeta}>
            {t("screening.itemCount", { count: inst.definition.items.length })}
          </Text>
        </Pressable>
      ))}
      {instruments !== null && instruments.length === 0 && (
        <Text style={[styles.consent, rtl && styles.rtl]}>{t("screening.loadError")}</Text>
      )}
      <View style={{ height: spacing.xl }} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  container: { padding: spacing.xl, gap: spacing.md, paddingTop: spacing.xl * 1.5 },
  title: { ...type.title, color: colors.textPrimary },
  consent: {
    ...type.body,
    color: colors.textPrimary,
    backgroundColor: colors.accentSoft,
    borderRadius: 12,
    padding: spacing.md,
  },
  arPending: { ...type.body, color: colors.textSecondary },
  card: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 14,
    padding: spacing.md,
    gap: spacing.xs,
  },
  cardTitle: { ...type.body, fontWeight: "600", color: colors.textPrimary },
  cardMeta: { fontSize: 14, color: colors.textSecondary },
  rtl: { textAlign: "right", writingDirection: "rtl" },
});
