/**
 * Crisis screen (spec §10.8). Full-screen, calm, works offline from cached
 * resources. Reachable from the persistent help affordance and auto-invoked
 * at L3 (Phase 2 wires the chat trigger).
 *
 * Honesty rules on this screen (N2/N4): Palio says it is an AI and cannot
 * call anyone; the numbers connect the user to real people.
 */
import { useRouter } from "expo-router";
import { useEffect, useState } from "react";
import {
  I18nManager,
  Linking,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { useTranslation } from "react-i18next";

import { getCrisisResources, type CrisisResources } from "../src/api/crisis";
import { isRTL } from "../src/i18n";
import { colors, spacing, type } from "../src/theme/tokens";

export default function CrisisScreen() {
  const { t, i18n } = useTranslation();
  const router = useRouter();
  const rtl = isRTL(i18n.language) || I18nManager.isRTL;
  const [resources, setResources] = useState<CrisisResources | null>(null);

  useEffect(() => {
    let mounted = true;
    getCrisisResources().then((r) => mounted && setResources(r));
    return () => {
      mounted = false;
    };
  }, []);

  const showLines = (resources?.lines ?? []).filter(
    (line) => !/placeholder/i.test(line.number),
  );

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.container}>
      <Text style={[styles.title, rtl && styles.rtl]}>{t("crisis.title")}</Text>
      <Text style={[styles.body, rtl && styles.rtl]}>{t("crisis.notAlone")}</Text>
      <Text style={[styles.body, rtl && styles.rtl]}>{t("crisis.aiHonesty")}</Text>
      <Text style={[styles.emergency, rtl && styles.rtl]}>{t("crisis.emergencyNow")}</Text>

      {resources && !resources.verified && (
        <View style={styles.devBanner}>
          <Text style={[styles.devBannerText, rtl && styles.rtl]}>
            {t("crisis.unverifiedBanner")}
          </Text>
        </View>
      )}

      {showLines.map((line) => (
        <Pressable
          key={`${line.name}-${line.number}`}
          style={styles.lineCard}
          accessibilityRole="button"
          accessibilityLabel={t("crisis.callLabel", { name: line.name })}
          onPress={() => Linking.openURL(`tel:${line.number.replace(/[^+0-9]/g, "")}`)}
        >
          <Text style={[styles.lineName, rtl && styles.rtl]}>{line.name}</Text>
          <Text style={[styles.lineNumber, rtl && styles.rtl]}>{line.number}</Text>
          <Text style={[styles.lineMeta, rtl && styles.rtl]}>{line.hours}</Text>
        </Pressable>
      ))}

      {showLines.length === 0 && resources && (
        <Text style={[styles.body, rtl && styles.rtl]}>{t("crisis.noLinesFallback")}</Text>
      )}

      <Pressable
        style={styles.backLink}
        accessibilityRole="button"
        onPress={() => router.back()}
      >
        <Text style={[styles.backText, rtl && styles.rtl]}>{t("crisis.back")}</Text>
      </Pressable>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.crisisSurface },
  container: { padding: spacing.xl, gap: spacing.md, paddingTop: spacing.xl * 2 },
  title: { ...type.title, color: colors.crisisText },
  body: { ...type.body, color: colors.textPrimary },
  emergency: { ...type.body, fontWeight: "700", color: colors.crisisText },
  devBanner: {
    backgroundColor: "#FBE9B7",
    borderRadius: 8,
    padding: spacing.sm,
  },
  devBannerText: { fontSize: 14, lineHeight: 20, color: "#6B5211" },
  lineCard: {
    backgroundColor: colors.surface,
    borderRadius: 14,
    padding: spacing.md,
    gap: spacing.xs,
    borderWidth: 1,
    borderColor: colors.border,
  },
  lineName: { ...type.body, fontWeight: "600", color: colors.textPrimary },
  lineNumber: { fontSize: 22, lineHeight: 30, color: colors.crisisText, fontWeight: "700" },
  lineMeta: { fontSize: 14, lineHeight: 20, color: colors.textSecondary },
  backLink: { marginTop: spacing.lg, alignSelf: "center", padding: spacing.sm },
  backText: { ...type.body, color: colors.textSecondary, textDecorationLine: "underline" },
  rtl: { textAlign: "right", writingDirection: "rtl" },
});
