import { useCallback, useEffect, useRef, useState } from "react";
import { message } from "./api";

export interface Loaded<T> {
  data: T | undefined;
  error: string | undefined;
  loading: boolean;
  reload: () => void;
}

/** Runs `load` on mount and whenever `reload` is called (and every `pollMs` when given); a failure becomes `error`, never a throw. */
export function useLoad<T>(load: () => Promise<T>, key: string, pollMs?: number): Loaded<T> {
  const [data, setData] = useState<T>();
  const [error, setError] = useState<string>();
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  const loader = useRef(load);
  loader.current = load;

  // biome-ignore lint/correctness/useExhaustiveDependencies: `key` and `tick` are the triggers; `load` is read through a ref
  useEffect(() => {
    let live = true;
    const run = () =>
      loader
        .current()
        .then((d) => {
          if (live) {
            setData(d);
            setError(undefined);
          }
        })
        .catch((e: unknown) => {
          if (live) {
            setData(undefined);
            setError(message(e));
          }
        })
        .finally(() => live && setLoading(false));
    setLoading(true);
    void run();
    const timer = pollMs ? setInterval(() => void run(), pollMs) : undefined;
    return () => {
      live = false;
      if (timer) clearInterval(timer);
    };
  }, [key, tick, pollMs]);

  const reload = useCallback(() => setTick((n) => n + 1), []);
  return { data, error, loading, reload };
}
