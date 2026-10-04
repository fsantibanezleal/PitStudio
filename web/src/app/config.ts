import { FolderGit2 } from "lucide-react";
import type { ArchitectureTab, ShellConfig } from "~/shell/config";
import { archTab } from "./architecture";

const ARCH_TABS = ["what", "lanes", "studio", "webflow", "science", "contracts", "tools"];

export const shellConfig: ShellConfig = {
  product: "PitStudio",
  repo: "PitStudio",
  author: "Felipe A. Santibanez-Leal",
  ...__BUILD_INFO__,
  repoUrl: "https://github.com/fsantibanezleal/PitStudio",
  routes: [
    { path: "/", labelKey: "nav.explore", end: true },
    { path: "/cases", labelKey: "nav.cases" },
    { path: "/studio", labelKey: "nav.studio" },
    { path: "/theory", labelKey: "nav.theory" },
    { path: "/methods", labelKey: "nav.methods" },
    { path: "/results", labelKey: "nav.results" },
    { path: "/knowledge", labelKey: "nav.knowledge" },
  ],
  links: [
    { href: "https://github.com/fsantibanezleal/PitStudio", labelKey: "links.github", icon: FolderGit2 },
  ],
  footer: {
    licenceKey: "footer.licence",
    provenance: [{ labelKey: "footer.provenanceNone" }],
  },
  architectureTabs: ARCH_TABS.map(
    (id): ArchitectureTab => ({ id, titleKey: `arch.${id}.title`, Content: archTab(id) }),
  ),
  access: { digest: __ACCESS_DIGEST__ },
};
