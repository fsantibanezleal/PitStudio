import { Info } from "lucide-react";
import { type ComponentType, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import styles from "./shell.module.css";

// The dialog (base-ui dialog and tabs, the diagrams) is its own chunk (NFR-018-02). The info button is on every page: it is a plain
// button until the chunk is in, and the chunk is requested once the page is idle after hydration, or at once when the pointer or the
// keyboard reaches the button. When the chunk is in, the dialog (with its own trigger in the same place) replaces the plain button.
const loadDialog = () => import("./ArchitectureDialog").then((m) => m.default);

/** The info button of the header and, once its chunk is in, the view of how the app works. */
export function ArchitectureModal() {
  const { t } = useTranslation("shell");
  const [Dialog, setDialog] = useState<ComponentType<{ openOnMount: boolean }> | null>(null);
  const pressed = useRef(false);

  useEffect(() => {
    let live = true;
    const load = () =>
      void loadDialog().then((component) => {
        if (live) setDialog(() => component);
      });
    const idle = window.requestIdleCallback ?? ((cb: () => void) => window.setTimeout(cb, 200));
    const handle = idle(load);
    return () => {
      live = false;
      if (window.cancelIdleCallback && typeof handle === "number") window.cancelIdleCallback(handle);
    };
  }, []);

  if (Dialog) return <Dialog openOnMount={pressed.current} />;
  const load = () => void loadDialog().then((component) => setDialog(() => component));
  return (
    <button
      type="button"
      className={styles.iconButton}
      aria-label={t("about")}
      aria-haspopup="dialog"
      onPointerEnter={load}
      onFocus={load}
      onClick={() => {
        pressed.current = true;
        load();
      }}
    >
      <Info aria-hidden="true" size={18} />
    </button>
  );
}
