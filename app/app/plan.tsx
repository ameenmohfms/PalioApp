/**
 * Plan screen (spec §10.6): active strategies with the try→rate→adapt loop,
 * the strategy library to pick from, and the single opt-in daily check-in
 * toggle (N5: max one, user-configured, no guilt framing).
 */
import { useEffect, useState } from "react";
import { I18nManager, Pressable, ScrollView, StyleSheet, Switch, Text, View } from "react-native";
import { useTranslation } from "react-i18next";
import * as SecureStore from "expo-secure-store";

import {
  adaptStrategy,
  assignStrategy,
  dropStrategy,
  fetchPlan,
  rateStrategy,
  type Plan,
  type Strategy,
} from "../src/api/coaching";
import { isRTL } from "../src/i18n";
import { disableDailyCheckin, enableDailyCheckin } from "../src/notifications/checkin";
import { colors, spacing, type } from "../src/theme/tokens";

const CHECKIN_KEY = "palio.checkin.enabled";

export default function PlanScreen() {
  const { t, i18n } = useTranslation();
  const rtl = isRTL(i18n.language) || I18nManager.isRTL;
  const [plan, setPlan] = useState<Plan | null>(null);
  const [checkin, setCheckin] = useState(false);

  async function reload() {
    setPlan(await fetchPlan());
  }

  useEffect(() => {
    let mounted = true;
    (async () => {
      const [nextPlan, stored] = await Promise.all([
        fetchPlan().catch(() => null),
        SecureStore.getItemAsync(CHECKIN_KEY).catch(() => null),
      ]);
      if (!mounted) return;
      if (nextPlan) setPlan(nextPlan);
      setCheckin(stored === "1");
    })();
    return () => {
      mounted = false;
    };
  }, []);

  async function toggleCheckin(value: boolean) {
    if (value) {
      const granted = await enableDailyCheckin(i18n.language);
      if (!granted) {
        setCheckin(false);
        return;
      }
    } else {
      await disableDailyCheckin();
    }
    setCheckin(value);
    await SecureStore.setItemAsync(CHECKIN_KEY, value ? "1" : "0");
  }

  const active = (plan?.strategies ?? []).filter((s) =>
    ["assigned", "adapted", "tried"].includes(s.status),
  );
  const activeKeys = new Set(active.map((s) => s.key));

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.container}>
      <Text style={[styles.title, rtl && styles.rtl]}>{t("plan.title")}</Text>

      {plan?.plan_summary && (
        <Text style={[styles.summary, rtl && styles.rtl]}>{plan.plan_summary}</Text>
      )}

      <View style={styles.checkinRow}>
        <Text style={[styles.body, rtl && styles.rtl, { flex: 1 }]}>
          {t("plan.checkinToggle")}
        </Text>
        <Switch value={checkin} onValueChange={toggleCheckin} />
      </View>

      <Text style={[styles.section, rtl && styles.rtl]}>{t("plan.activeSection")}</Text>
      {active.length === 0 && (
        <Text style={[styles.meta, rtl && styles.rtl]}>{t("plan.noActive")}</Text>
      )}
      {active.map((s) => (
        <StrategyCard key={s.id} strategy={s} rtl={rtl} onChanged={reload} />
      ))}

      <Text style={[styles.section, rtl && styles.rtl]}>{t("plan.librarySection")}</Text>
      {(plan?.library ?? [])
        .filter((entry) => !activeKeys.has(entry.key))
        .map((entry) => (
          <View key={entry.key} style={styles.card}>
            <Text style={[styles.cardTitle, rtl && styles.rtl]}>{entry.title}</Text>
            <Text style={[styles.meta, rtl && styles.rtl]}>{entry.summary}</Text>
            <Pressable
              style={styles.smallCta}
              accessibilityRole="button"
              onPress={() => assignStrategy(entry.key).then(reload)}
            >
              <Text style={styles.smallCtaText}>{t("plan.tryThis")}</Text>
            </Pressable>
          </View>
        ))}
      <View style={{ height: spacing.xl * 2 }} />
    </ScrollView>
  );
}

function StrategyCard({
  strategy,
  rtl,
  onChanged,
}: {
  strategy: Strategy;
  rtl: boolean;
  onChanged: () => Promise<void>;
}) {
  const { t } = useTranslation();
  return (
    <View style={styles.card}>
      <Text style={[styles.cardTitle, rtl && styles.rtl]}>{strategy.title}</Text>
      <Text style={[styles.meta, rtl && styles.rtl]}>{strategy.try_this_week}</Text>
      {strategy.steps.map((step, i) => (
        <Text key={i} style={[styles.step, rtl && styles.rtl]}>
          {i + 1}. {step}
        </Text>
      ))}
      <View style={styles.actions}>
        <Pressable
          style={styles.smallCta}
          accessibilityRole="button"
          onPress={() => rateStrategy(strategy.id, "helped").then(onChanged)}
        >
          <Text style={styles.smallCtaText}>👍 {t("plan.helped")}</Text>
        </Pressable>
        <Pressable
          style={styles.smallCta}
          accessibilityRole="button"
          onPress={() => rateStrategy(strategy.id, "partial").then(onChanged)}
        >
          <Text style={styles.smallCtaText}>{t("plan.partly")}</Text>
        </Pressable>
        <Pressable
          style={styles.smallCta}
          accessibilityRole="button"
          onPress={() => rateStrategy(strategy.id, "did_not_help").then(onChanged)}
        >
          <Text style={styles.smallCtaText}>👎 {t("plan.didntHelp")}</Text>
        </Pressable>
      </View>
      {strategy.status === "tried" && (
        <View style={styles.actions}>
          <Pressable
            style={styles.smallGhost}
            accessibilityRole="button"
            onPress={() => adaptStrategy(strategy.id).then(onChanged)}
          >
            <Text style={styles.smallGhostText}>{t("plan.adapt")}</Text>
          </Pressable>
          <Pressable
            style={styles.smallGhost}
            accessibilityRole="button"
            onPress={() => dropStrategy(strategy.id).then(onChanged)}
          >
            <Text style={styles.smallGhostText}>{t("plan.swap")}</Text>
          </Pressable>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  container: { padding: spacing.xl, gap: spacing.md, paddingTop: spacing.xl * 1.5 },
  title: { ...type.title, color: colors.textPrimary },
  summary: {
    ...type.body,
    color: colors.textPrimary,
    backgroundColor: colors.accentSoft,
    borderRadius: 12,
    padding: spacing.md,
  },
  body: { ...type.body, color: colors.textPrimary },
  meta: { fontSize: 14, lineHeight: 21, color: colors.textSecondary },
  step: { fontSize: 15, lineHeight: 24, color: colors.textPrimary },
  section: { fontSize: 18, fontWeight: "600", color: colors.textPrimary, marginTop: spacing.sm },
  checkinRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 12,
    padding: spacing.md,
  },
  card: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 14,
    padding: spacing.md,
    gap: spacing.sm,
  },
  cardTitle: { ...type.body, fontWeight: "600", color: colors.textPrimary },
  actions: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  smallCta: {
    backgroundColor: colors.accentSoft,
    borderRadius: 10,
    paddingVertical: spacing.xs + 2,
    paddingHorizontal: spacing.sm + 2,
  },
  smallCtaText: { fontSize: 14, color: colors.textPrimary, fontWeight: "600" },
  smallGhost: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 10,
    paddingVertical: spacing.xs + 2,
    paddingHorizontal: spacing.sm + 2,
  },
  smallGhostText: { fontSize: 14, color: colors.textSecondary },
  rtl: { textAlign: "right", writingDirection: "rtl" },
});
