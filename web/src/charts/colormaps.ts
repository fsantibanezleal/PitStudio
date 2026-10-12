// Perceptually ordered colour maps for rasters and heat maps (FR-020-12: the chart module holds no hex literal; the colour
// stops are RGB triples). `sequential` is a viridis-like map, `diverging` a blue-white-red map for signed fields.

export type Rgb = readonly [number, number, number];
export type ColormapName = "sequential" | "diverging";

const STOPS: Record<ColormapName, readonly Rgb[]> = {
  sequential: [
    [68, 1, 84],
    [72, 40, 120],
    [62, 74, 137],
    [49, 104, 142],
    [38, 130, 142],
    [31, 158, 137],
    [53, 183, 121],
    [109, 205, 89],
    [180, 222, 44],
    [253, 231, 37],
  ],
  diverging: [
    [33, 102, 172],
    [67, 147, 195],
    [146, 197, 222],
    [209, 229, 240],
    [247, 247, 247],
    [253, 219, 199],
    [244, 165, 130],
    [214, 96, 77],
    [178, 24, 43],
  ],
};

/** The colour at position t in [0, 1] (clamped; NaN gives the first stop), linearly interpolated between the stops. */
export function colormap(name: ColormapName, t: number): Rgb {
  const stops = STOPS[name];
  const u = Number.isFinite(t) ? Math.min(1, Math.max(0, t)) : 0;
  const pos = u * (stops.length - 1);
  const i = Math.min(stops.length - 2, Math.floor(pos));
  const f = pos - i;
  const a = stops[i] as Rgb;
  const b = stops[i + 1] as Rgb;
  return [
    Math.round(a[0] + f * (b[0] - a[0])),
    Math.round(a[1] + f * (b[1] - a[1])),
    Math.round(a[2] + f * (b[2] - a[2])),
  ];
}

/** `rgb(r, g, b)` text for a canvas or CSS. */
export function rgbText(color: Rgb): string {
  return `rgb(${color[0]}, ${color[1]}, ${color[2]})`;
}
