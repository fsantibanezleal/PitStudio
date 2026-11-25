// The view of a chart: the visible range of each axis (linear or logarithmic) and the size of the plot area in CSS pixels.
// Screen y points down. Zooming is about a screen point (the data point under the cursor stays under it) and panning moves the
// content with the pointer; both are affine in the plotted coordinate (the value on a linear axis, its logarithm on a log axis).

export type Scale = "linear" | "log";

export interface Axis {
  min: number;
  max: number;
  scale: Scale;
}

export interface View {
  x: Axis;
  y: Axis;
  width: number;
  height: number;
}

const finite = (n: unknown): n is number => typeof n === "number" && Number.isFinite(n);

function checkAxis(name: string, axis: Axis): void {
  if (!axis || (axis.scale !== "linear" && axis.scale !== "log")) {
    throw new RangeError(`${name}.scale must be "linear" or "log"`);
  }
  if (!finite(axis.min) || !finite(axis.max)) throw new RangeError(`${name} range must be finite`);
  if (axis.scale === "log" && axis.min <= 0) throw new RangeError(`${name}.min must be > 0 on a log axis`);
  if (axis.min >= axis.max) throw new RangeError(`${name}.min must be below ${name}.max`);
}

export function makeView(view: View): View {
  if (!finite(view?.width) || view.width <= 0) throw new RangeError("width must be a finite number > 0");
  if (!finite(view.height) || view.height <= 0) throw new RangeError("height must be a finite number > 0");
  checkAxis("x", view.x);
  checkAxis("y", view.y);
  return {
    x: { min: view.x.min, max: view.x.max, scale: view.x.scale },
    y: { min: view.y.min, max: view.y.max, scale: view.y.scale },
    width: view.width,
    height: view.height,
  };
}

const plotted = (axis: Axis, value: number): number => (axis.scale === "log" ? Math.log(value) : value);
const unplotted = (axis: Axis, value: number): number => (axis.scale === "log" ? Math.exp(value) : value);

/** Fraction t in [0, 1] of the axis (from min to max) to the data value. */
function fromFraction(axis: Axis, t: number): number {
  if (axis.scale === "linear") return axis.min + t * (axis.max - axis.min);
  const lo = Math.log(axis.min);
  return Math.exp(lo + t * (Math.log(axis.max) - lo));
}

function toFraction(axis: Axis, value: number): number {
  if (axis.scale === "linear") return (value - axis.min) / (axis.max - axis.min);
  const lo = Math.log(axis.min);
  return (Math.log(value) - lo) / (Math.log(axis.max) - lo);
}

export function toData(view: View, px: number, py: number): { x: number; y: number } {
  const y =
    view.y.scale === "linear"
      ? view.y.max - (py / view.height) * (view.y.max - view.y.min)
      : fromFraction(view.y, 1 - py / view.height);
  return { x: fromFraction(view.x, px / view.width), y };
}

export function toScreen(view: View, x: number, y: number): { px: number; py: number } {
  return { px: toFraction(view.x, x) * view.width, py: (1 - toFraction(view.y, y)) * view.height };
}

function zoomAxis(axis: Axis, factor: number, fraction: number): Axis {
  const lo = plotted(axis, axis.min);
  const hi = plotted(axis, axis.max);
  const d = lo + fraction * (hi - lo);
  const nlo = d - (d - lo) / factor;
  const nhi = d + (hi - d) / factor;
  return { min: unplotted(axis, nlo), max: unplotted(axis, nhi), scale: axis.scale };
}

/** factor > 1 zooms in about the screen point: the range of each axis is divided by factor (in log space on a log axis). */
export function zoomAt(view: View, factor: number, px: number, py: number): View {
  if (!finite(factor) || factor <= 0)
    throw new RangeError(`factor must be a finite number > 0, got ${String(factor)}`);
  return {
    x: zoomAxis(view.x, factor, px / view.width),
    y: zoomAxis(view.y, factor, 1 - py / view.height),
    width: view.width,
    height: view.height,
  };
}

function shiftAxis(axis: Axis, fractionShift: number): Axis {
  const lo = plotted(axis, axis.min);
  const hi = plotted(axis, axis.max);
  const delta = fractionShift * (hi - lo);
  return { min: unplotted(axis, lo + delta), max: unplotted(axis, hi + delta), scale: axis.scale };
}

/** The content follows the pointer: moving it right by dpx moves the visible x range left by dpx / width of the range. */
export function pan(view: View, dpx: number, dpy: number): View {
  return {
    x: shiftAxis(view.x, -dpx / view.width),
    y: shiftAxis(view.y, dpy / view.height),
    width: view.width,
    height: view.height,
  };
}
