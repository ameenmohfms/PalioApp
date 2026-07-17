/**
 * The single opt-in daily check-in (spec §10.9, Hard Rule N5).
 *
 * Constraints enforced here, not just by convention:
 * - exactly ONE scheduled notification, ever (we cancel all before scheduling)
 * - calm, invitation-framed copy — no streaks, guilt, or loss framing
 * - purely local: no push infra, no server-side schedule (N9)
 */
import * as Notifications from "expo-notifications";

const DEFAULT_HOUR = 19; // 7pm local; user-adjustable in a later settings pass

const COPY: Record<string, { title: string; body: string }> = {
  ar: {
    title: "باليو",
    body: "لحظة اطمئنان إذا حاب — كيف كان يومك؟",
  },
  en: {
    title: "Palio",
    body: "A gentle check-in if you'd like one — how did today go?",
  },
};

export async function enableDailyCheckin(locale: string, hour = DEFAULT_HOUR): Promise<boolean> {
  const { status } = await Notifications.requestPermissionsAsync();
  if (status !== "granted") return false;

  // N5: never more than one scheduled notification.
  await Notifications.cancelAllScheduledNotificationsAsync();
  const copy = COPY[locale.slice(0, 2)] ?? COPY.en;
  await Notifications.scheduleNotificationAsync({
    content: { title: copy.title, body: copy.body },
    trigger: {
      type: Notifications.SchedulableTriggerInputTypes.DAILY,
      hour,
      minute: 0,
    },
  });
  return true;
}

export async function disableDailyCheckin(): Promise<void> {
  await Notifications.cancelAllScheduledNotificationsAsync();
}
