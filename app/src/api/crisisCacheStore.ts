/**
 * Tiny persistent KV used only for the crisis-resource cache.
 * SecureStore is available and adds encryption at rest for free; crisis
 * numbers aren't secret, but reusing the one storage primitive we already
 * ship keeps the dependency set minimal (N9-adjacent hygiene).
 */
import * as SecureStore from "expo-secure-store";

export default {
  async getItem(key: string): Promise<string | null> {
    return SecureStore.getItemAsync(key.replace(/[^\w.-]/g, "_"));
  },
  async setItem(key: string, value: string): Promise<void> {
    await SecureStore.setItemAsync(key.replace(/[^\w.-]/g, "_"), value);
  },
};
