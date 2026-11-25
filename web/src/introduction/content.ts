import executiveJson from "../../content/executive.json";

/** The executive view data, exactly the committed `web/content/executive.json` (validated against the shell schema in its test). */
export const executive = executiveJson;

/** The ids of the five sub-tabs of the shell's ExecutiveView, in their fixed order (the shell owns this definition). */
export const EXECUTIVE_SECTIONS = ["pain", "context", "situation", "trends", "proposal"] as const;

export type ExecutiveSection = (typeof EXECUTIVE_SECTIONS)[number];

export function isExecutiveSection(value: string | null): value is ExecutiveSection {
  return value !== null && (EXECUTIVE_SECTIONS as readonly string[]).includes(value);
}
