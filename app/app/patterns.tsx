/**
 * Patterns & Progress (spec §10.5): suggestion-card confirmation queue,
 * the living map (wins & strengths rendered first — progress framing, not
 * a pathology wall), and screener trend bars. Every node is editable and
 * hard-deletable by the user (§8 user controls).
 */
import { useCallback, useEffect, useState } from "react";
import {
  I18nManager,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { useTranslation } from "react-i18next";

import {
  confirmPattern,
  deletePattern,
  editPattern,
  listPatterns,
  rejectPattern,
  screenerHistory,
  type PatternNode,
  type PatternsListing,
  type ScreenerHistoryItem,
} from "../src/api/patterns";
import { isRTL } from "../src/i18n";
import { colors, spacing, type } from "../src/theme/tokens";

const TYPE_ORDER: PatternNode["type"][] = [
  "win",
  "strength",
  "strategy_outcome",
  "trigger",
  "context",
];

export default function PatternsScreen() {
  const { t, i18n } = useTranslation();
  const rtl = isRTL(i18n.language) || I18nManager.isRTL;
  const [listing, setListing] = useState<PatternsListing | null>(null);
  const [trends, setTrends] = useState<ScreenerHistoryItem[]>([]);

  const reload = useCallback(async () => {
    const [patterns, history] = await Promise.all([
      listPatterns().catch(() => null),
      screenerHistory().catch(() => []),
    ]);
    if (patterns) setListing(patterns);
    setTrends(history.filter((h) => h.completed));
  }, []);

  useEffect(() => {
    let mounted = true;
    (async () => {
      if (mounted) await reload();
    })();
    return () => {
      mounted = false;
    };
  }, [reload]);

  const grouped = TYPE_ORDER.map((typeKey) => ({
    typeKey,
    nodes: (listing?.confirmed ?? []).filter((p) => p.type === typeKey),
  })).filter((g) => g.nodes.length > 0);

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.container}>
      <Text style={[styles.title, rtl && styles.rtl]}>{t("patterns.title")}</Text>

      {(listing?.proposed ?? []).length > 0 && (
        <>
          <Text style={[styles.section, rtl && styles.rtl]}>{t("patterns.suggestions")}</Text>
          {listing!.proposed.map((node) => (
            <SuggestionCard key={node.id} node={node} rtl={rtl} onChanged={reload} />
          ))}
        </>
      )}

      <Text style={[styles.section, rtl && styles.rtl]}>{t("patterns.mapSection")}</Text>
      {grouped.length === 0 && (
        <Text style={[styles.meta, rtl && styles.rtl]}>{t("patterns.empty")}</Text>
      )}
      {grouped.map(({ typeKey, nodes }) => (
        <View key={typeKey} style={styles.group}>
          <Text style={[styles.groupTitle, rtl && styles.rtl]}>
            {t(`patterns.types.${typeKey}`)}
          </Text>
          {nodes.map((node) => (
            <ConfirmedNode key={node.id} node={node} rtl={rtl} onChanged={reload} />
          ))}
        </View>
      ))}

      {trends.length > 0 && (
        <>
          <Text style={[styles.section, rtl && styles.rtl]}>{t("patterns.trends")}</Text>
          <TrendBars trends={trends} rtl={rtl} />
        </>
      )}
      <View style={{ height: spacing.xl * 2 }} />
    </ScrollView>
  );
}

function SuggestionCard({
  node,
  rtl,
  onChanged,
}: {
  node: PatternNode;
  rtl: boolean;
  onChanged: () => Promise<void>;
}) {
  const { t } = useTranslation();
  const [text, setText] = useState(node.text);
  return (
    <View style={styles.suggestion}>
      <Text style={[styles.meta, rtl && styles.rtl]}>
        {t("patterns.noticedPrefix")} · {t(`patterns.types.${node.type}`)}
      </Text>
      <TextInput
        style={[styles.editInput, rtl && styles.rtl]}
        value={text}
        onChangeText={setText}
        multiline
      />
      <View style={styles.actions}>
        <Pressable
          style={styles.smallCta}
          accessibilityRole="button"
          onPress={async () => {
            if (text !== node.text) await editPattern(node.id, text);
            await confirmPattern(node.id);
            await onChanged();
          }}
        >
          <Text style={styles.smallCtaText}>{t("patterns.accurate")}</Text>
        </Pressable>
        <Pressable
          style={styles.smallGhost}
          accessibilityRole="button"
          onPress={async () => {
            await rejectPattern(node.id);
            await onChanged();
          }}
        >
          <Text style={styles.smallGhostText}>{t("patterns.notAccurate")}</Text>
        </Pressable>
      </View>
    </View>
  );
}

function ConfirmedNode({
  node,
  rtl,
  onChanged,
}: {
  node: PatternNode;
  rtl: boolean;
  onChanged: () => Promise<void>;
}) {
  const { t } = useTranslation();
  return (
    <View style={styles.node}>
      <Text style={[styles.body, rtl && styles.rtl, { flex: 1 }]}>{node.text}</Text>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={t("patterns.delete")}
        onPress={async () => {
          await deletePattern(node.id);
          await onChanged();
        }}
      >
        <Text style={styles.deleteText}>✕</Text>
      </Pressable>
    </View>
  );
}

function TrendBars({ trends, rtl }: { trends: ScreenerHistoryItem[]; rtl: boolean }) {
  const byInstrument = new Map<string, ScreenerHistoryItem[]>();
  for (const item of trends) {
    const list = byInstrument.get(item.instrument_key) ?? [];
    list.push(item);
    byInstrument.set(item.instrument_key, list);
  }
  const maxByKey: Record<string, number> = { phq9: 27, gad7: 21, asrs_v1_1: 6 };
  return (
    <View style={{ gap: spacing.md }}>
      {[...byInstrument.entries()].map(([key, items]) => {
        const ordered = [...items].reverse();
        const max = maxByKey[key] ?? 30;
        return (
          <View key={key} style={styles.trendCard}>
            <Text style={[styles.groupTitle, rtl && styles.rtl]}>{key}</Text>
            <View style={styles.trendRow}>
              {ordered.map((item) => {
                const score =
                  item.scores.total ?? item.scores.part_a_shaded ?? 0;
                const height = Math.max(6, (score / max) * 72);
                return (
                  <View key={item.id} style={styles.trendCol}>
                    <View style={[styles.trendBar, { height }]} />
                    <Text style={styles.trendLabel}>{score}</Text>
                  </View>
                );
              })}
            </View>
          </View>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  container: { padding: spacing.xl, gap: spacing.md, paddingTop: spacing.xl * 1.5 },
  title: { ...type.title, color: colors.textPrimary },
  section: { fontSize: 18, fontWeight: "600", color: colors.textPrimary, marginTop: spacing.sm },
  body: { ...type.body, color: colors.textPrimary },
  meta: { fontSize: 14, lineHeight: 21, color: colors.textSecondary },
  suggestion: {
    backgroundColor: colors.accentSoft,
    borderRadius: 14,
    padding: spacing.md,
    gap: spacing.sm,
  },
  editInput: {
    backgroundColor: colors.surface,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.sm,
    fontSize: 16,
    color: colors.textPrimary,
  },
  actions: { flexDirection: "row", gap: spacing.sm },
  smallCta: {
    backgroundColor: colors.accent,
    borderRadius: 10,
    paddingVertical: spacing.xs + 2,
    paddingHorizontal: spacing.md,
  },
  smallCtaText: { fontSize: 14, color: colors.surface, fontWeight: "600" },
  smallGhost: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 10,
    paddingVertical: spacing.xs + 2,
    paddingHorizontal: spacing.md,
  },
  smallGhostText: { fontSize: 14, color: colors.textSecondary },
  group: { gap: spacing.sm },
  groupTitle: { fontSize: 15, fontWeight: "600", color: colors.textSecondary },
  node: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 12,
    padding: spacing.md,
  },
  deleteText: { fontSize: 16, color: colors.textSecondary, padding: spacing.xs },
  trendCard: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 12,
    padding: spacing.md,
    gap: spacing.sm,
  },
  trendRow: { flexDirection: "row", alignItems: "flex-end", gap: spacing.sm },
  trendCol: { alignItems: "center", gap: 2 },
  trendBar: { width: 18, borderRadius: 4, backgroundColor: colors.accent },
  trendLabel: { fontSize: 12, color: colors.textSecondary },
  rtl: { textAlign: "right", writingDirection: "rtl" },
});
