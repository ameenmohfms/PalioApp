/**
 * Report & Referrals (spec §10.7): generate/share the clinician summary and
 * browse the operator-verified directory. The UI states clearly these are
 * options, not endorsements. Medications appear in the report ONLY if the
 * user types them here (§9).
 */
import { useEffect, useState } from "react";
import {
  I18nManager,
  Linking,
  Pressable,
  ScrollView,
  Share,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { useTranslation } from "react-i18next";

import {
  generateReport,
  listReferrals,
  setCity,
  tapReferral,
  type Referral,
} from "../src/api/care";
import { isRTL } from "../src/i18n";
import { colors, spacing, type } from "../src/theme/tokens";

export default function CareScreen() {
  const { t, i18n } = useTranslation();
  const rtl = isRTL(i18n.language) || I18nManager.isRTL;
  const [meds, setMeds] = useState("");
  const [reportUrl, setReportUrl] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [city, setCityInput] = useState("");
  const [referrals, setReferrals] = useState<Referral[]>([]);

  useEffect(() => {
    let mounted = true;
    listReferrals()
      .then((rows) => mounted && setReferrals(rows))
      .catch(() => {});
    return () => {
      mounted = false;
    };
  }, []);

  async function makeReport() {
    setBusy(true);
    try {
      const { downloadUrl } = await generateReport({
        language: i18n.language.startsWith("ar") ? "ar" : "en",
        userMedications: meds.trim() || undefined,
      });
      setReportUrl(downloadUrl);
      await Share.share({ message: downloadUrl });
    } catch {
      setReportUrl(null);
    } finally {
      setBusy(false);
    }
  }

  async function applyCity() {
    await setCity(city.trim());
    setReferrals(await listReferrals(city.trim() || undefined));
  }

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.container}>
      <Text style={[styles.title, rtl && styles.rtl]}>{t("care.title")}</Text>

      <Text style={[styles.section, rtl && styles.rtl]}>{t("care.reportSection")}</Text>
      <Text style={[styles.meta, rtl && styles.rtl]}>{t("care.reportNote")}</Text>
      <TextInput
        style={[styles.input, rtl && styles.rtl]}
        placeholder={t("care.medsPlaceholder")}
        placeholderTextColor={colors.textSecondary}
        value={meds}
        onChangeText={setMeds}
        multiline
      />
      <Pressable
        style={[styles.cta, busy && styles.ctaDisabled]}
        accessibilityRole="button"
        disabled={busy}
        onPress={makeReport}
      >
        <Text style={styles.ctaText}>{t("care.generate")}</Text>
      </Pressable>
      {reportUrl && (
        <Pressable accessibilityRole="button" onPress={() => Linking.openURL(reportUrl)}>
          <Text style={[styles.link, rtl && styles.rtl]}>{t("care.openReport")}</Text>
        </Pressable>
      )}

      <Text style={[styles.section, rtl && styles.rtl]}>{t("care.referralSection")}</Text>
      <Text style={[styles.meta, rtl && styles.rtl]}>{t("care.notEndorsements")}</Text>
      <View style={styles.cityRow}>
        <TextInput
          style={[styles.input, rtl && styles.rtl, { flex: 1 }]}
          placeholder={t("care.cityPlaceholder")}
          placeholderTextColor={colors.textSecondary}
          value={city}
          onChangeText={setCityInput}
        />
        <Pressable style={styles.smallCta} accessibilityRole="button" onPress={applyCity}>
          <Text style={styles.smallCtaText}>{t("care.applyCity")}</Text>
        </Pressable>
      </View>
      {referrals.map((ref) => (
        <Pressable
          key={ref.id}
          style={styles.card}
          accessibilityRole="button"
          onPress={() => {
            tapReferral(ref.id).catch(() => {});
            if (/^https?:/.test(ref.contact)) Linking.openURL(ref.contact);
          }}
        >
          <Text style={[styles.cardTitle, rtl && styles.rtl]}>{ref.name}</Text>
          <Text style={[styles.meta, rtl && styles.rtl]}>
            {ref.type} · {ref.city}
            {ref.telehealth ? ` · ${t("care.telehealth")}` : ""}
          </Text>
          <Text style={[styles.meta, rtl && styles.rtl]}>{ref.contact}</Text>
        </Pressable>
      ))}
      {referrals.length === 0 && (
        <Text style={[styles.meta, rtl && styles.rtl]}>{t("care.noReferrals")}</Text>
      )}
      <View style={{ height: spacing.xl * 2 }} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  container: { padding: spacing.xl, gap: spacing.md, paddingTop: spacing.xl * 1.5 },
  title: { ...type.title, color: colors.textPrimary },
  section: { fontSize: 18, fontWeight: "600", color: colors.textPrimary, marginTop: spacing.sm },
  meta: { fontSize: 14, lineHeight: 21, color: colors.textSecondary },
  input: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 12,
    padding: spacing.md,
    fontSize: 16,
    color: colors.textPrimary,
    backgroundColor: colors.surface,
  },
  cityRow: { flexDirection: "row", gap: spacing.sm, alignItems: "center" },
  cta: {
    backgroundColor: colors.accent,
    borderRadius: 14,
    padding: spacing.md,
    alignItems: "center",
  },
  ctaDisabled: { opacity: 0.45 },
  ctaText: { fontSize: 16, fontWeight: "600", color: colors.surface },
  smallCta: {
    backgroundColor: colors.accentSoft,
    borderRadius: 10,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
  },
  smallCtaText: { fontSize: 14, fontWeight: "600", color: colors.textPrimary },
  link: { ...type.body, color: colors.accent, textDecorationLine: "underline" },
  card: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 14,
    padding: spacing.md,
    gap: spacing.xs,
  },
  cardTitle: { ...type.body, fontWeight: "600", color: colors.textPrimary },
  rtl: { textAlign: "right", writingDirection: "rtl" },
});
