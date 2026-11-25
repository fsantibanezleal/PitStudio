import { Dialog } from "@base-ui/react/dialog";
import { Tabs } from "@base-ui/react/tabs";
import { Info, X } from "lucide-react";
import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { useShellConfig } from "./config";
import styles from "./shell.module.css";

/** The info view: how the app and the repository behind it work, one tab per aspect. A chunk of its own (see ArchitectureModal). */
export default function ArchitectureDialog({ openOnMount }: { openOnMount: boolean }) {
  const { architectureTabs } = useShellConfig();
  const { t } = useTranslation("shell");
  const { t: tApp } = useTranslation("app");
  const first = architectureTabs[0]?.id;
  const trigger = useRef<HTMLButtonElement | null>(null);
  // the visitor pressed the plain button before this chunk was in: open as that press would
  useEffect(() => {
    if (openOnMount) trigger.current?.click();
  }, [openOnMount]);

  return (
    <Dialog.Root>
      <Dialog.Trigger ref={trigger} className={styles.iconButton} aria-label={t("about")}>
        <Info aria-hidden="true" size={18} />
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Backdrop className={styles.backdrop} />
        <Dialog.Popup className={styles.modal}>
          <div className={styles.modalHeader}>
            <Dialog.Title className={styles.modalTitle}>{t("arch.title")}</Dialog.Title>
            <Dialog.Close className={styles.iconButton} aria-label={t("arch.close")}>
              <X aria-hidden="true" size={18} />
            </Dialog.Close>
          </div>
          <Dialog.Description className={styles.muted}>{t("arch.description")}</Dialog.Description>
          <Tabs.Root defaultValue={first} className={styles.tabs}>
            <Tabs.List className={styles.tabList} aria-label={t("arch.tabs")} activateOnFocus>
              {architectureTabs.map((tab) => (
                <Tabs.Tab key={tab.id} value={tab.id} className={styles.tab}>
                  {tApp(tab.titleKey)}
                </Tabs.Tab>
              ))}
            </Tabs.List>
            {architectureTabs.map(({ id, Content }) => (
              <Tabs.Panel key={id} value={id} className={styles.tabPanel}>
                <Content />
              </Tabs.Panel>
            ))}
          </Tabs.Root>
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
