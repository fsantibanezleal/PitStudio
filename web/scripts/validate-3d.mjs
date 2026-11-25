// Runs the reference validators of FR-016-19 on one file and prints a JSON report: { "errors": [...], "warnings": [...] }.
//   node scripts/validate-3d.mjs glb <file.glb>          Khronos glTF Validator (npm `gltf-validator`, pinned in package.json)
//   node scripts/validate-3d.mjs tileset <tileset.json>  CesiumGS 3D Tiles Validator (npm `3d-tiles-validator`, pinned in package.json)
// Exit code: 0 no error, 1 at least one error, 2 usage or a validator that could not run. Warnings never change the exit code.
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { basename, dirname, resolve } from "node:path";

const require = createRequire(import.meta.url);

const ERROR = 0;
const WARNING = 1;

function finish(errors, warnings) {
  process.stdout.write(`${JSON.stringify({ errors, warnings })}\n`);
  process.exitCode = errors.length > 0 ? 1 : 0;
}

async function validateGlb(file) {
  const validator = require("gltf-validator");
  const bytes = new Uint8Array(readFileSync(file));
  const dir = dirname(resolve(file));
  const report = await validator.validateBytes(bytes, {
    uri: basename(file),
    maxIssues: 200,
    externalResourceFunction: (uri) =>
      Promise.resolve(new Uint8Array(readFileSync(resolve(dir, decodeURIComponent(uri))))),
  });
  const line = (m) => `${m.code}: ${m.message} (${m.pointer ?? ""})`;
  const messages = report.issues.messages;
  finish(
    messages.filter((m) => m.severity === ERROR).map(line),
    messages.filter((m) => m.severity === WARNING).map(line),
  );
}

async function validateTileset(file) {
  const { Validators } = require("3d-tiles-validator");
  const result = await Validators.validateTilesetFile(resolve(file));
  const errors = [];
  const warnings = [];
  for (let i = 0; i < result.length; i++) {
    const issue = result.get(i);
    const text = `${issue.type}: ${issue.message} (${issue.path})`;
    if (issue.severity === "ERROR") errors.push(text);
    else if (issue.severity === "WARNING") warnings.push(text);
  }
  finish(errors, warnings);
}

async function main() {
  const [mode, file] = process.argv.slice(2);
  if (!file || (mode !== "glb" && mode !== "tileset")) {
    process.stderr.write("usage: node scripts/validate-3d.mjs glb|tileset <file>\n");
    process.exitCode = 2;
    return;
  }
  try {
    await (mode === "glb" ? validateGlb(file) : validateTileset(file));
  } catch (e) {
    process.stderr.write(`validator could not run: ${e?.message ?? e}\n`);
    process.exitCode = 2;
  }
}

await main();
