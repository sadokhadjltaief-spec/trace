import ReactMarkdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'

const components: Components = {
  h1: ({ children }) => <h3 className="mt-4 text-lg font-bold text-foreground first:mt-0">{children}</h3>,
  h2: ({ children }) => <h3 className="mt-4 text-base font-bold text-foreground first:mt-0">{children}</h3>,
  h3: ({ children }) => <h4 className="mt-3 font-semibold text-foreground first:mt-0">{children}</h4>,
  p: ({ children }) => <p className="leading-relaxed [&:not(:first-child)]:mt-3">{children}</p>,
  ul: ({ children }) => <ul className="mt-2 flex list-disc flex-col gap-1 ps-5 marker:text-primary">{children}</ul>,
  ol: ({ children }) => <ol className="mt-2 flex list-decimal flex-col gap-1 ps-5 marker:font-semibold marker:text-primary">{children}</ol>,
  strong: ({ children }) => <strong className="font-semibold text-foreground">{children}</strong>,
  a: ({ children, href }) =>
    href && /\/engine\/media\/[a-f0-9]+\.mp4$/.test(href) ? (
      // educational video made by the engine (slides + narration): played in place, subtitles track alongside
      <span className="mt-3 block overflow-hidden rounded-2xl border border-border bg-black shadow-sm">
        <video controls preload="metadata" className="aspect-video w-full" src={href}>
          <track kind="subtitles" src={href.replace(/\.mp4$/, '.vtt')} default />
        </video>
        <span className="block bg-card px-4 py-2 text-sm font-semibold text-foreground">{children}</span>
      </span>
    ) : (
      <a href={href} target="_blank" rel="noreferrer" className="font-medium text-accent-foreground underline underline-offset-4">
        {children}
      </a>
    ),
  img: ({ src, alt }) => (
    // diagrams drawn by the engine (computed with matplotlib, never AI-generated pixels)
    <a href={typeof src === 'string' ? src : undefined} target="_blank" rel="noreferrer" className="mt-3 block overflow-hidden rounded-2xl border border-border bg-white shadow-sm">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={typeof src === 'string' ? src : undefined} alt={alt ?? ''} className="w-full" loading="lazy" />
    </a>
  ),
  code: ({ children }) => (
    <code className="rounded-md bg-muted px-1.5 py-0.5 font-mono text-[0.85em] text-foreground">{children}</code>
  ),
  pre: ({ children }) => (
    <pre className="mt-3 overflow-x-auto rounded-xl bg-muted p-4 text-sm [&_code]:bg-transparent [&_code]:p-0" dir="ltr">
      {children}
    </pre>
  ),
  blockquote: ({ children }) => <blockquote className="mt-3 border-s-4 border-primary/50 ps-4 italic">{children}</blockquote>,
  table: ({ children }) => (
    <div className="mt-3 overflow-x-auto rounded-xl border border-border">
      <table className="w-full border-collapse text-sm">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-muted text-foreground">{children}</thead>,
  th: ({ children }) => <th className="border-b border-border px-3 py-2 text-start font-semibold">{children}</th>,
  td: ({ children }) => <td className="border-b border-border px-3 py-2 align-top last:border-b-0">{children}</td>,
}

export function Markdown({ children }: { children: string }) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
      {children}
    </ReactMarkdown>
  )
}
