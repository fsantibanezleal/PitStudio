import { highlight } from "./search";

/** Text with the occurrences of the query wrapped in `mark` elements; the text itself stays escaped text. */
export function Marked({ text, query }: { text: string; query: string }) {
  const parts = highlight(text, query);
  let offset = 0;
  return (
    <>
      {parts.map((p) => {
        const key = offset;
        offset += p.text.length;
        return p.match ? <mark key={key}>{p.text}</mark> : <span key={key}>{p.text}</span>;
      })}
    </>
  );
}
