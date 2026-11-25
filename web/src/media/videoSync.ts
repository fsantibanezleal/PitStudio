// Video and clock agree to within two frame periods (FR-018-24); further apart, the video is re-seeked to the clock.

/** True iff |mediaTime - clockTime| > 2 / fps. A non-finite time never asks for a re-seek. */
export function needsReseek(mediaTime: number, clockTime: number, fps: number): boolean {
  if (!Number.isFinite(mediaTime) || !Number.isFinite(clockTime) || !(fps > 0)) return false;
  return Math.abs(mediaTime - clockTime) > 2 / fps;
}
