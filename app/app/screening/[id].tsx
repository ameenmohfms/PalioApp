/**
 * Screening runner (spec §7/§10.4): one fixed card per item, verbatim text
 * (A3), progress indicator, pausable (answers persist server-side per item;
 * leaving and returning starts a fresh pass but prior completed results are
 * kept). Never interprets mid-instrument. Formulation renders at the end —
 * the only channel for results.
 */
import { useLocalSearchParams, useRouter } from "expo-router";
import { useEffect, useState } from "react";
import { I18nManager, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useTranslation } from "react-i18next";

import {
  answerItem,
  completeScreening,
  listInstruments,
  startScreening,
  type Formulation,
  type Instrument,
} from "../../src/api/screeners";
import { isRTL } from "../../src/i18n";
import { colors, spacing, type } from "../../src/theme/tokens";

export default function ScreeningRunner() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { t, i18n } = useTranslation();
  const router = useRouter();
  const rtl = isRTL(i18n.language) || I18nManager.isRTL;

  const [instrument, setInstrument] = useState<Instrument | null>(null);
  const [resultId, setResultId] = useState<string | null>(null);
  const [index, setIndex] = useState(0);
  const [formulationResult, setFormulation] = useState<Formulation | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let mounted = true;
    (async () => {
      const list = await listInstruments();
      const inst = list.find((x) => x.id === id);
      if (!inst || !mounted) return;
      setInstrument(inst);
      const rid = await startScreening(inst.id);
      if (mounted) setResultId(rid);
    })().catch(() => mounted && setError(true));
    return () => {
      mounted = false;
    };
  }, [id]);

  if (error) {
    return (
      <View style={styles.center}>
        <Text style={styles.body}>{t("screening.loadError")}</Text>
      </View>
    );
  }
  if (!instrument || !resultId) {
    return (
      <View style={styles.center}>
        <Text style={styles.body}>{t("common.loading")}</Text>
      </View>
    );
  }

  if (formulationResult) {
    return (
      <ScrollView style={styles.screen} contentContainerStyle={styles.container}>
        <Text style={[styles.title, rtl && styles.rtl]}>{t("screening.resultTitle")}</Text>
        <Text style={[styles.body, rtl && styles.rtl]}>
          {formulationResult.reported_summary}
        </Text>
        <Text style={[styles.body, rtl && styles.rtl]}>{formulationResult.score_meaning}</Text>
        <Text style={[styles.honest, rtl && styles.rtl]}>{formulationResult.honest_line}</Text>
        {formulationResult.ui_action === "show_resources" && (
          <Pressable
            style={styles.resources}
            accessibilityRole="button"
            onPress={() => router.push("/crisis")}
          >
            <Text style={[styles.body, rtl && styles.rtl]}>{t("chat.resourcesBanner")}</Text>
          </Pressable>
        )}
        <Text style={[styles.meta, rtl && styles.rtl]}>
          {t("screening.rescreen", { days: formulationResult.rescreen_days })}
        </Text>
        <Pressable
          style={styles.cta}
          accessibilityRole="button"
          onPress={() => router.replace("/chat")}
        >
          <Text style={styles.ctaText}>{t("screening.backToChat")}</Text>
        </Pressable>
      </ScrollView>
    );
  }

  const items = instrument.definition.items;
  const item = items[index];
  const progress = `${index + 1} / ${items.length}`;

  async function choose(value: number) {
    if (!resultId || !instrument) return;
    const current = instrument.definition.items[index];
    try {
      await answerItem(resultId, current.id, value);
      if (index + 1 < instrument.definition.items.length) {
        setIndex(index + 1);
      } else {
        setFormulation(await completeScreening(resultId));
      }
    } catch {
      setError(true);
    }
  }

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.container}>
      <Text style={[styles.meta, rtl && styles.rtl]}>
        {instrument.title} · {progress}
      </Text>
      <View style={styles.progressTrack}>
        <View style={[styles.progressFill, { width: `${((index + 1) / items.length) * 100}%` }]} />
      </View>
      {index === 0 && (
        <Text style={[styles.body, rtl && styles.rtl]}>
          {instrument.definition.instructions}
        </Text>
      )}
      {/* Verbatim item text in a fixed card (Hard Rule A3). */}
      <View style={styles.itemCard}>
        <Text style={styles.itemText}>{item.text}</Text>
      </View>
      <View style={styles.options}>
        {instrument.definition.scale.map((opt) => (
          <Pressable
            key={opt.value}
            style={styles.option}
            accessibilityRole="button"
            onPress={() => choose(opt.value)}
          >
            <Text style={styles.optionText}>{opt.label}</Text>
          </Pressable>
        ))}
      </View>
      <Pressable
        style={styles.pause}
        accessibilityRole="button"
        onPress={() => router.back()}
      >
        <Text style={[styles.meta, rtl && styles.rtl]}>{t("screening.pause")}</Text>
      </Pressable>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  container: { padding: spacing.xl, gap: spacing.md, paddingTop: spacing.xl * 1.5 },
  title: { ...type.title, color: colors.textPrimary },
  body: { ...type.body, color: colors.textPrimary },
  meta: { fontSize: 14, color: colors.textSecondary },
  progressTrack: {
    height: 6,
    borderRadius: 3,
    backgroundColor: colors.border,
    overflow: "hidden",
  },
  progressFill: { height: 6, backgroundColor: colors.accent },
  itemCard: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 14,
    padding: spacing.lg,
  },
  itemText: { fontSize: 19, lineHeight: 30, color: colors.textPrimary },
  options: { gap: spacing.sm },
  option: {
    borderWidth: 1,
    borderColor: colors.accent,
    borderRadius: 12,
    padding: spacing.md,
    backgroundColor: colors.surface,
  },
  optionText: { fontSize: 16, color: colors.textPrimary, textAlign: "center" },
  honest: {
    ...type.body,
    fontWeight: "600",
    color: colors.textPrimary,
    backgroundColor: colors.accentSoft,
    borderRadius: 12,
    padding: spacing.md,
  },
  resources: {
    backgroundColor: colors.crisisSurface,
    borderRadius: 12,
    padding: spacing.md,
  },
  cta: {
    backgroundColor: colors.accent,
    borderRadius: 14,
    padding: spacing.md,
    alignItems: "center",
    marginTop: spacing.md,
  },
  ctaText: { fontSize: 17, fontWeight: "600", color: colors.surface },
  pause: { alignSelf: "center", padding: spacing.sm, marginTop: spacing.sm },
  rtl: { textAlign: "right", writingDirection: "rtl" },
});
