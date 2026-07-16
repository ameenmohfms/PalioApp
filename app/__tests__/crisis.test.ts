import * as fs from "fs";
import * as path from "path";

import bundledAppCopy from "../src/config/crisis_resources.sa.json";

test("bundled crisis config stays in sync with the operator config", () => {
  const rootConfig = JSON.parse(
    fs.readFileSync(
      path.resolve(__dirname, "../../config/crisis_resources.sa.json"),
      "utf-8",
    ),
  );
  expect(bundledAppCopy).toEqual(rootConfig);
});

test("crisis locale strings state AI honesty and emergency guidance (N2/N4)", () => {
  const ar = require("../src/i18n/locales/ar.json");
  const en = require("../src/i18n/locales/en.json");
  expect(ar.crisis.aiHonesty).toContain("ذكاء اصطناعي");
  expect(ar.crisis.aiHonesty).toContain("ما يقدر يتصل");
  expect(en.crisis.aiHonesty).toMatch(/AI/);
  expect(en.crisis.aiHonesty).toMatch(/cannot call/);
  expect(ar.crisis.emergencyNow).toContain("الطوارئ");
  expect(en.crisis.emergencyNow).toMatch(/emergency services/);
});
