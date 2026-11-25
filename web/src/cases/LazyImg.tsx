import { type ImgHTMLAttributes, useEffect, useRef, useState } from "react";

/**
 * An image that is requested when it nears the viewport (NFR-018-01): the `src` is set once the element is within 200 px of the
 * visible area, so a still below the fold is not part of the first view. Without `IntersectionObserver` it is set at once. The
 * `width` and `height` attributes keep the box in place so the page does not jump when the image arrives.
 */
export function LazyImg({
  src,
  ...rest
}: Omit<ImgHTMLAttributes<HTMLImageElement>, "src" | "loading"> & { src: string }) {
  const ref = useRef<HTMLImageElement | null>(null);
  const [near, setNear] = useState(typeof IntersectionObserver === "undefined");

  useEffect(() => {
    const el = ref.current;
    if (near || !el) return;
    if (typeof IntersectionObserver === "undefined") {
      setNear(true);
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setNear(true);
          observer.disconnect();
        }
      },
      { rootMargin: "200px 0px" },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [near]);

  // biome-ignore lint/a11y/useAltText: the caller passes `alt` through the props
  return <img ref={ref} decoding="async" {...rest} {...(near ? { src } : {})} />;
}
