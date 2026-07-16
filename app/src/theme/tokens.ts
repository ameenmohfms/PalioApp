/**
 * Design tokens: calm, spacious, WCAG-AA contrast (spec §10).
 * No gamification colors, no urgency reds outside the crisis screen.
 */
export const colors = {
  background: "#F7F5F0",
  surface: "#FFFFFF",
  textPrimary: "#1F2933",
  textSecondary: "#52606D",
  accent: "#2F6F5E",
  accentSoft: "#DDEBE6",
  border: "#D9D4CB",
  // Crisis screen only — calm, high-contrast, not alarm-red.
  crisisSurface: "#FDF3F2",
  crisisText: "#7A2E2A",
} as const;

export const spacing = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 40,
} as const;

export const type = {
  // Dyslexia-friendly option toggles a wider line height + spacing preset (§10).
  body: { fontSize: 17, lineHeight: 26 },
  bodyComfort: { fontSize: 18, lineHeight: 32, letterSpacing: 0.4 },
  title: { fontSize: 26, lineHeight: 34, fontWeight: "600" as const },
} as const;
