import { Dialog } from "@base-ui/react/dialog";
import { Tabs } from "@base-ui/react/tabs";
import { Info, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useShellConfig } from "./config";
import styles from "./shell.module.css";

/** The ⓘ view: how the app and the repository behind it work, one tab per aspect. */
export function ArchitectureModal() {
  const { architectureTabs } = useShellConfig();
  const { t } = useTranslation("shell");
  const { t: tApp } = useTranslation("app");
  const first = architectureTabs[0]?.id;

  return (
    <Dialog.Root>
      <Dialog.Trigger className={styles.iconButton} aria-label={t("about")}>
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
            <Tabs.List className={styles.tabList} aria-label={t("arch.tabs")}>
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
