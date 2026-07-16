/**
 * Chat screen (spec §10.3): RTL-correct message list with streaming-style
 * reveal of Sentinel-approved replies. Crisis ui_action navigates to the
 * full-screen crisis view; L2 shows a calm resources banner.
 */
import { useRouter } from "expo-router";
import { useEffect, useRef, useState } from "react";
import {
  FlatList,
  I18nManager,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { useTranslation } from "react-i18next";

import { createSession, fetchHistory, sendMessage } from "../src/api/client";
import { revealSteps } from "../src/chat/reveal";
import { isRTL } from "../src/i18n";
import { colors, spacing, type } from "../src/theme/tokens";

type Bubble = { id: string; role: "user" | "assistant"; content: string };

export default function Chat() {
  const { t, i18n } = useTranslation();
  const router = useRouter();
  const rtl = isRTL(i18n.language) || I18nManager.isRTL;

  const [sessionId, setSessionId] = useState<string | null>(null);
  const [bubbles, setBubbles] = useState<Bubble[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [showResources, setShowResources] = useState(false);
  const listRef = useRef<FlatList<Bubble>>(null);

  useEffect(() => {
    let mounted = true;
    (async () => {
      const id = await createSession();
      if (!mounted) return;
      setSessionId(id);
      const history = await fetchHistory(id);
      if (!mounted) return;
      setBubbles(
        history.map((h) => ({ id: h.id, role: h.role as Bubble["role"], content: h.content })),
      );
    })().catch(() => {});
    return () => {
      mounted = false;
    };
  }, []);

  async function send() {
    const text = input.trim();
    if (!text || !sessionId || busy) return;
    setInput("");
    setBusy(true);
    const userBubble: Bubble = { id: `u-${Date.now()}`, role: "user", content: text };
    setBubbles((prev) => [...prev, userBubble]);
    try {
      const turn = await sendMessage(sessionId, text);
      if (turn.ui_action === "crisis_screen") {
        router.push("/crisis");
      }
      if (turn.ui_action === "show_resources") {
        setShowResources(true);
      }
      const replyId = `a-${Date.now()}`;
      // Progressive reveal of the approved text (PLAN C1).
      for (const step of revealSteps(turn.reply, 24)) {
        setBubbles((prev) => [
          ...prev.filter((b) => b.id !== replyId),
          { id: replyId, role: "assistant", content: step },
        ]);
         
        await new Promise((resolve) => setTimeout(resolve, 24));
      }
    } catch {
      setBubbles((prev) => [
        ...prev,
        { id: `e-${Date.now()}`, role: "assistant", content: t("chat.sendError") },
      ]);
    } finally {
      setBusy(false);
      listRef.current?.scrollToEnd({ animated: true });
    }
  }

  return (
    <KeyboardAvoidingView
      style={styles.screen}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <View style={styles.header}>
        <Text style={styles.headerTitle}>{t("app.name")}</Text>
        <Pressable
          accessibilityRole="button"
          onPress={() => router.push("/screening")}
          style={styles.headerLink}
        >
          <Text style={styles.headerLinkText}>{t("screening.openList")}</Text>
        </Pressable>
      </View>
      {showResources && (
        <Pressable
          style={styles.resourcesBanner}
          accessibilityRole="button"
          onPress={() => router.push("/crisis")}
        >
          <Text style={[styles.resourcesText, rtl && styles.rtl]}>
            {t("chat.resourcesBanner")}
          </Text>
        </Pressable>
      )}
      <FlatList
        ref={listRef}
        style={styles.list}
        contentContainerStyle={styles.listContent}
        data={bubbles}
        keyExtractor={(b) => b.id}
        onContentSizeChange={() => listRef.current?.scrollToEnd({ animated: false })}
        renderItem={({ item }) => (
          <View
            style={[
              styles.bubble,
              item.role === "user" ? styles.userBubble : styles.assistantBubble,
            ]}
          >
            <Text style={[styles.bubbleText, rtl && styles.rtl]}>{item.content}</Text>
          </View>
        )}
      />
      <View style={styles.inputRow}>
        <TextInput
          style={[styles.input, rtl && styles.rtl]}
          placeholder={t("chat.inputPlaceholder")}
          placeholderTextColor={colors.textSecondary}
          value={input}
          onChangeText={setInput}
          multiline
          accessibilityLabel={t("chat.inputPlaceholder")}
        />
        <Pressable
          style={[styles.send, (!input.trim() || busy) && styles.sendDisabled]}
          accessibilityRole="button"
          accessibilityLabel={t("chat.send")}
          disabled={!input.trim() || busy}
          onPress={send}
        >
          <Text style={styles.sendText}>{t("chat.send")}</Text>
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: spacing.md,
    paddingTop: spacing.xl,
    paddingBottom: spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  headerTitle: { fontSize: 18, fontWeight: "600", color: colors.textPrimary },
  headerLink: { padding: spacing.xs },
  headerLinkText: { fontSize: 15, color: colors.accent, fontWeight: "600" },
  resourcesBanner: {
    backgroundColor: colors.accentSoft,
    padding: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  resourcesText: { ...type.body, color: colors.textPrimary },
  list: { flex: 1 },
  listContent: { padding: spacing.md, gap: spacing.sm, paddingBottom: spacing.xl },
  bubble: { maxWidth: "85%", borderRadius: 16, padding: spacing.md },
  userBubble: { alignSelf: "flex-end", backgroundColor: colors.accentSoft },
  assistantBubble: {
    alignSelf: "flex-start",
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
  },
  bubbleText: { ...type.body, color: colors.textPrimary },
  inputRow: {
    flexDirection: "row",
    alignItems: "flex-end",
    gap: spacing.sm,
    padding: spacing.md,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    backgroundColor: colors.background,
  },
  input: {
    flex: 1,
    minHeight: 44,
    maxHeight: 130,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 14,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    fontSize: 17,
    color: colors.textPrimary,
    backgroundColor: colors.surface,
  },
  send: {
    backgroundColor: colors.accent,
    borderRadius: 14,
    paddingVertical: spacing.sm + 2,
    paddingHorizontal: spacing.md,
  },
  sendDisabled: { opacity: 0.45 },
  sendText: { color: colors.surface, fontWeight: "600", fontSize: 16 },
  rtl: { textAlign: "right", writingDirection: "rtl" },
});
