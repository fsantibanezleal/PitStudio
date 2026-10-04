import { Mountain } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link, NavLink } from "react-router";
import { ArchitectureModal } from "./ArchitectureModal";
import { useShellConfig } from "./config";
import { LanguageSwitcher } from "./LanguageSwitcher";
import styles from "./shell.module.css";
import { ThemeToggle } from "./ThemeToggle";

export function Header() {
  const { product, routes, links } = useShellConfig();
  const { t } = useTranslation("shell");

  return (
    <header className={styles.header}>
      <div className={styles.headerInner}>
        <Link to="/" className={styles.brand} aria-label={t("home")}>
          <Mountain aria-hidden="true" size={22} />
          <span>{product}</span>
        </Link>
        <nav aria-label={t("nav.label")} className={styles.nav}>
          <ul>
            {routes.map((route) => (
              <li key={route.path}>
                <NavLink to={route.path} end={route.end} prefetch="intent">
                  {t(route.labelKey)}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
        <div className={styles.tools}>
          {links.map(({ href, labelKey, icon: Icon }) => (
            <a key={href} href={href} className={styles.iconButton} aria-label={t(labelKey)} rel="noopener">
              <Icon aria-hidden="true" size={18} />
            </a>
          ))}
          <ArchitectureModal />
          <LanguageSwitcher />
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}
