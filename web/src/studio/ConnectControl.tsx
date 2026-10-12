import { type FormEvent, useId, useState } from "react";
import { useTranslation } from "react-i18next";
import styles from "./studio.module.css";
import { type ConnectResult, connectLocal, validatePort } from "./connect";

/** The opt-in control: nothing is requested on render or while typing, one request per valid press (FR-019-44). */
export function ConnectControl({ fetchImpl, timeoutMs }: { fetchImpl?: typeof fetch; timeoutMs?: number }) {
  const { t } = useTranslation("studio");
  const id = useId();
  const [text, setText] = useState("");
  const [invalid, setInvalid] = useState(false);
  const [result, setResult] = useState<ConnectResult | null>(null);

  const press = async (event: FormEvent) => {
    event.preventDefault();
    const port = validatePort(text);
    if (port === null) {
      setInvalid(true);
      return;
    }
    setInvalid(false);
    setResult(await connectLocal(port, { fetchImpl, timeoutMs }));
  };

  return (
    <form className={styles.connect} onSubmit={press} noValidate>
      <label htmlFor={`${id}-port`}>{t("connect.port")}</label>
      <input
        id={`${id}-port`}
        data-testid="connect-port"
        inputMode="numeric"
        autoComplete="off"
        value={text}
        aria-invalid={invalid}
        aria-describedby={invalid ? `${id}-error` : undefined}
        onChange={(e) => setText(e.target.value)}
      />
      <button type="submit" data-testid="connect-button">
        {t("connect.button")}
      </button>
      {invalid && (
        <span id={`${id}-error`} role="alert" data-testid="connect-error" className={styles.error}>
          {t("connect.invalid")}
        </span>
      )}
      <span data-testid="connect-label" aria-live="polite">
        {result === null
          ? ""
          : result.connected
            ? t("connect.connected", { version: result.version })
            : t("connect.notConnected")}
      </span>
    </form>
  );
}
