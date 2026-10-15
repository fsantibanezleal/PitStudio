// The shapes of the knowledge bundle the sections read (DC-020-03, `contracts/knowledge-bundle.schema.json`).
export interface ParameterRow {
  id: string;
  module: string;
  quantity?: string;
  value?: number | string;
  range?: { min: number; max: number };
  units: string;
  si?: { value?: number | string; range?: { min: number; max: number }; unit: string };
  citation: string;
  page?: string;
  verification: string;
  verified_on?: string;
  symbols?: string[];
}

export interface EquationRow {
  id: string;
  title: string;
  module?: string;
  latex: string;
  /** KaTeX HTML and MathML rendered at build time; the client never renders LaTeX. */
  html?: string;
  symbols: Array<{ symbol: string; meaning: string; units: string }>;
  function?: string;
  citation?: string;
  page?: string;
  verification: string;
  theory?: { topic: string; anchor: string };
  engine?: { id: string; spec?: string };
}

export interface GlossaryEntry {
  id: string;
  origin?: string;
  term_en: string;
  term_es: string;
  definition_en: string;
  definition_es: string;
  citation?: string;
}

export interface DatasetRow {
  id: string;
  title?: string;
  kind: string;
  spdx: string;
  redistribution: string;
  landing_url?: string;
  card?: string;
}

export interface FrameworkRow {
  id: string;
  name: string;
  category: string;
  status: string;
  licence_class?: string;
}

export interface BibliographyRow {
  key: string;
  entry_type?: string;
  authors?: string;
  title: string;
  year?: number | string;
  doi?: string;
  url?: string;
  access?: string;
  cited_by?: { parameters?: string[]; equations?: string[] };
}

export interface KnowledgeBundle {
  schema_version?: string;
  source: { minephys_version: string; minephys_commit: string };
  parameters: ParameterRow[];
  equations: EquationRow[];
  glossary: GlossaryEntry[];
  datasets: DatasetRow[];
  frameworks: FrameworkRow[];
  bibliography: BibliographyRow[];
}

export const SECTIONS = [
  "glossary",
  "equations",
  "parameters",
  "datasets",
  "frameworks",
  "bibliography",
] as const;
export type SectionId = (typeof SECTIONS)[number];

/** A link target that is safe to put in an href: only https URLs. */
export function httpsUrl(url: unknown): string | undefined {
  if (typeof url !== "string") return undefined;
  try {
    const u = new URL(url);
    return u.protocol === "https:" ? u.href : undefined;
  } catch {
    return undefined;
  }
}
