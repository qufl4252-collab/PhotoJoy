import { getApp } from "firebase/app";
import {
  getDatabase,
  get,
  ref,
  child,
  runTransaction,
} from "firebase/database";

export function accountCloud(vault, db = getDatabase(getApp())) {
  const root = ref(db, "rosters/" + vault.owner);
  return {
    async read() {
      vault.check();
      const snapshot = await get(root);
      vault.check();
      return snapshot.val() || {};
    },
    async merge(key, value) {
      vault.check();
      const target = child(root, key);
      const result = await runTransaction(
        target,
        (current) => {
          vault.check();
          if (current && current.rev >= value.rev) return;
          return value;
        },
        { applyLocally: false },
      );
      vault.check();
      return result.snapshot.val();
    },
  };
}
