// DC-018-01 `kpi_unit` ids (ASCII) -> the display symbols docs/cases/README.md writes in its catalogue.
const SYMBOLS: Record<string, string> = {
  "1": "",
  km2: "km²",
  m3: "m³",
  "m3/shift": "m³/shift",
  "L/(t.km)": "L/(t·km)",
  "ug/m3": "µg/m³",
};

/** Display symbol of a unit id; an id without a special symbol is shown as written, dimensionless "1" as nothing. */
export function unitSymbol(unit: string): string {
  return Object.hasOwn(SYMBOLS, unit) ? (SYMBOLS[unit] as string) : unit;
}
