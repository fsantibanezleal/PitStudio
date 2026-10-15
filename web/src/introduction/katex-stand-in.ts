/**
 * The shared shell imports `katex` for its Equation and InlineMath components. The executive view never renders an
 * equation (its writing rules forbid them), and the real library would add about 75 KB gzip to the start page, which
 * is the Introduction. vite.config.ts points `katex` here; any attempt to typeset text shows it as plain text.
 */
const escapeHtml = (text: string): string =>
  text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

export default {
  renderToString: (text: string): string => `<span>${escapeHtml(text)}</span>`,
};
