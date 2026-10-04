import { LockKeyhole } from "lucide-react";
import { type FormEvent, type ReactNode, useEffect, useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { useShellConfig } from "./config";
import { accessKey, matchesDigest } from "./digest";
import styles from "./shell.module.css";

type GateState = "checking" | "locked" | "open";

/**
 * Soft access gate: the passphrase is compared with a build-time SHA-256 digest. It is UX, not
 * security — the UI says so. With an empty digest the gate is off.
 */
export function AccessGate({ children }: { children: ReactNode }) {
  const { repo, access } = useShellConfig();
  const { t } = useTranslation("shell");
  const [state, setState] = useState<GateState>(access.digest ? "checking" : "open");
  const [error, setError] = useState(false);
  const inputId = useId();
  const errorId = useId();

  useEffect(() => {
    if (!access.digest) return;
    let stored: string | null = null;
    try {
      stored = sessionStorage.getItem(accessKey(repo));
    } catch {
      // storage blocked: ask every time
    }
    setState(stored === access.digest ? "open" : "locked");
  }, [repo, access.digest]);

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const phrase = String(new FormData(event.currentTarget).get("passphrase") ?? "");
    if (await matchesDigest(phrase, access.digest)) {
      try {
        sessionStorage.setItem(accessKey(repo), access.digest);
      } catch {
        // storage blocked: open for this page only
      }
      setError(false);
      setState("open");
    } else {
      setError(true);
    }
  };

  if (state === "open") return <>{children}</>;
  if (state === "checking") {
    return (
      <p className={styles.checking} role="status">
        {t("gate.checking")}
      </p>
    );
  }
  return (
    <section className={styles.gate} aria-labelledby={`${inputId}-title`}>
      <LockKeyhole aria-hidden="true" size={28} />
      <h1 id={`${inputId}-title`}>{t("gate.title")}</h1>
      <p className={styles.notice}>{t("gate.notice")}</p>
      <form onSubmit={onSubmit} className={styles.gateForm}>
        <label htmlFor={inputId}>{t("gate.label")}</label>
        <input
          id={inputId}
          name="passphrase"
          type="password"
          autoComplete="off"
          required
          aria-invalid={error}
          aria-describedby={error ? errorId : undefined}
        />
        <button type="submit" className={styles.primaryButton}>
          {t("gate.submit")}
        </button>
        {error && (
          <p id={errorId} className={styles.error} role="alert">
            {t("gate.error")}
          </p>
        )}
      </form>
    </section>
  );
}
