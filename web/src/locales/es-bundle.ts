// The Spanish resources as one module, so that they travel as one chunk read by `shell/i18n.ts` when the language is first switched to Spanish.
import app from "./es/app.json";
import cases from "./es/cases.json";
import charts from "./es/charts.json";
import results from "./es/results.json";
import shell from "./es/shell.json";
import studio from "./es/studio.json";
import surrogates from "./es/surrogates.json";
import terrain3d from "./es/terrain3d.json";

export default { shell, app, cases, results, charts, surrogates, studio, terrain3d };
