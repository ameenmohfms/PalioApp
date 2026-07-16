import { revealSteps } from "../src/chat/reveal";

test("reveal steps end with the full text and grow monotonically", () => {
  const text = "هذا نص تجريبي للعرض التدريجي في المحادثة";
  const steps = revealSteps(text, 7);
  expect(steps[steps.length - 1]).toBe(text);
  for (let i = 1; i < steps.length; i++) {
    expect(steps[i].startsWith(steps[i - 1])).toBe(true);
  }
});

test("empty text yields a single empty step", () => {
  expect(revealSteps("")).toEqual([""]);
});
