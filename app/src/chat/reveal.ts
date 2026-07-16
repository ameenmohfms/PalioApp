/**
 * Streaming presentation (PLAN C1): the reply arrives fully
 * Sentinel-approved; the UI reveals it progressively so reading feels live
 * without safety ever trailing the stream.
 */
export function revealSteps(text: string, chunk = 12): string[] {
  if (!text) return [""];
  const steps: string[] = [];
  for (let i = chunk; i < text.length; i += chunk) {
    steps.push(text.slice(0, i));
  }
  steps.push(text);
  return steps;
}
