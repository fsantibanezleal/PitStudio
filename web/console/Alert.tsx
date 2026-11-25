import { useTranslation } from "react-i18next";

/** One failure message; the console stays usable around it. Text only: nothing from the API is ever rendered as markup. */
export function Alert({ text }: { text: string | undefined }) {
  const { t } = useTranslation();
  if (!text) return null;
  return (
    <p role="alert" className="alert">
      {t("error", { message: text })}
    </p>
  );
}
