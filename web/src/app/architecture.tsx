import { type ComponentType, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { inlineDiagram } from "./inlineSvg";

// One docs diagram per tab of the ⓘ view (FR-020-43). Loaded when its tab opens, so the diagrams stay out of the
// initial scripts of every route.
const DIAGRAMS: Record<string, () => Promise<{ default: string }>> = {
  what: () => import("../../../docs/assets/diagrams/pitstudio-overview.svg?raw"),
  lanes: () => import("../../../docs/assets/diagrams/lanes-measured-gate.svg?raw"),
  studio: () => import("../../../docs/assets/diagrams/studio-environment-map.svg?raw"),
  webflow: () => import("../../../docs/assets/diagrams/web-routes.svg?raw"),
  science: () => import("../../../docs/assets/diagrams/pipeline-stages.svg?raw"),
  contracts: () => import("../../../docs/assets/diagrams/manifest-contract.svg?raw"),
  tools: () => import("../../../docs/assets/diagrams/tool-map.svg?raw"),
};

/** Text and themed diagram of one ⓘ tab. */
export function archTab(id: string): ComponentType {
  function ArchTab() {
    const { t } = useTranslation("app");
    const [svg, setSvg] = useState<string | null>(null);
    useEffect(() => {
      let live = true;
      DIAGRAMS[id]?.().then((m) => {
        if (live) setSvg(inlineDiagram(m.default));
      });
      return () => {
        live = false;
      };
    }, []);
    return (
      <>
        <p>{t(`arch.${id}.body`)}</p>
        {/* Build-time repository file (guarded by tools/check_inline_svg.py), never user input. */}
        {/* biome-ignore lint/security/noDangerouslySetInnerHtml: inlined docs diagram, see above */}
        {svg && <div dangerouslySetInnerHTML={{ __html: svg }} />}
      </>
    );
  }
  ArchTab.displayName = `ArchTab(${id})`;
  return ArchTab;
}
