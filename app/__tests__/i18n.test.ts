import ar from "../src/i18n/locales/ar.json";
import en from "../src/i18n/locales/en.json";
import { DEFAULT_LOCALE, initI18n, isRTL } from "../src/i18n";

function keysOf(obj: Record<string, unknown>, prefix = ""): string[] {
  return Object.entries(obj).flatMap(([k, v]) =>
    typeof v === "object" && v !== null
      ? keysOf(v as Record<string, unknown>, `${prefix}${k}.`)
      : [`${prefix}${k}`],
  );
}

test("arabic is the default locale", () => {
  expect(DEFAULT_LOCALE).toBe("ar");
  expect(isRTL(DEFAULT_LOCALE)).toBe(true);
  expect(isRTL("en")).toBe(false);
});

test("ar and en catalogs have identical keys — no untranslated locale", () => {
  expect(keysOf(ar).sort()).toEqual(keysOf(en).sort());
});

test("capability disclosure (A4) exists in both languages and names AI + no-diagnosis + no-emergencies", () => {
  const i18n = initI18n("ar");
  expect(i18n.t("welcome.disclosure")).toContain("ذكاء اصطناعي");
  expect(i18n.t("welcome.disclosure")).toContain("تشخيص");
  const enText = en.welcome.disclosure;
  expect(enText).toMatch(/AI/);
  expect(enText).toMatch(/does not diagnose/);
  expect(enText).toMatch(/emergencies/);
});
