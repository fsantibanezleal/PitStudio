// The marker of the console build. Every file of the public Pages artifact is scanned for it (tools/check_pages_artifact.py):
// console code must never ship there. It is rendered as an attribute so the bundler keeps it.
export const BUILD_MARKER = "pitstudio-console-build";
