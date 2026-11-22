import type { LucideIcon } from "lucide-react";
import type { ComponentType } from "react";
import { createContext, useContext } from "react";

/** A top-level navigation entry. `labelKey` is a key in the shell's i18n namespace. */
export interface ShellRoute {
  path: string;
  labelKey: string;
  end?: boolean;
}

export interface ShellLink {
  href: string;
  labelKey: string;
  icon: LucideIcon;
}

export interface ProvenanceItem {
  labelKey: string;
  href?: string;
  /** Interpolation values of the label, e.g. `{ count }` for a plural key. */
  values?: Record<string, string | number>;
}

/** One tab of the ⓘ architecture modal. */
export interface ArchitectureTab {
  id: string;
  titleKey: string;
  Content: ComponentType;
}

/**
 * Everything the shared shell needs from an app. The shell owns chrome, access, language, theme
 * and honesty notices; the app owns its pages.
 */
export interface ShellConfig {
  product: string;
  repo: string;
  author: string;
  version: string;
  gitSha: string;
  buildDate: string;
  repoUrl: string;
  routes: ShellRoute[];
  links: ShellLink[];
  footer: {
    licenceKey: string;
    provenance: ProvenanceItem[];
    /** A hook that gives the provenance items from published data; it replaces `provenance` when present. */
    useProvenance?: () => ProvenanceItem[];
  };
  architectureTabs: ArchitectureTab[];
  /** SHA-256 hex of the demo passphrase. Empty string → the gate is off. */
  access: { digest: string };
}

export const ShellConfigContext = createContext<ShellConfig | null>(null);

export function useShellConfig(): ShellConfig {
  const config = useContext(ShellConfigContext);
  if (!config) throw new Error("useShellConfig must be used inside <ShellConfigContext.Provider>");
  return config;
}
