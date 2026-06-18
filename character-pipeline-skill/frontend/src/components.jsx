import React, { useState } from 'react'

// Tiny inline formatter: **bold** and *italic* → spans. Keeps plan.js copy clean.
export function RichText({ text }) {
  const parts = []
  let rest = String(text)
  const re = /(\*\*[^*]+\*\*|\*[^*]+\*)/g
  let last = 0
  let m
  while ((m = re.exec(rest))) {
    if (m.index > last) parts.push(rest.slice(last, m.index))
    const tok = m[0]
    if (tok.startsWith('**')) parts.push(<b key={m.index}>{tok.slice(2, -2)}</b>)
    else parts.push(<i key={m.index}>{tok.slice(1, -1)}</i>)
    last = re.lastIndex
  }
  if (last < rest.length) parts.push(rest.slice(last))
  return <>{parts}</>
}

export function CopyButton({ getText, label = 'copy' }) {
  const [state, setState] = useState(label)
  const onClick = () => {
    const text = typeof getText === 'function' ? getText() : getText
    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(text).then(
        () => {
          setState('copied ✓')
          setTimeout(() => setState(label), 1600)
        },
        () => setState('select + ⌘C'),
      )
    } else {
      setState('select + ⌘C')
    }
  }
  return (
    <button className={`copy ${state.startsWith('copied') ? 'ok' : ''}`} onClick={onClick} type="button">
      {state}
    </button>
  )
}

export function CodeBlock({ children, copy = true }) {
  const text = typeof children === 'string' ? children : ''
  return (
    <div className="codeblock">
      {copy && <CopyButton getText={text} />}
      <code>{children}</code>
    </div>
  )
}

export function Panel({ kicker, kickerNote, accent, brass, children }) {
  return (
    <div className={`panel ${accent ? 'accent' : ''} ${brass ? 'brass' : ''}`}>
      {kicker && (
        <h3>
          {kicker}
          {kickerNote && <span className="n"> — {kickerNote}</span>}
        </h3>
      )}
      {children}
    </div>
  )
}

export function KV({ rows }) {
  return (
    <dl className="kv">
      {rows.map((r, i) => (
        <React.Fragment key={i}>
          <dt>{r.k}</dt>
          <dd style={r.mono ? { fontFamily: 'var(--mono)', color: 'var(--sage)' } : undefined}>
            <RichText text={r.v} />
          </dd>
        </React.Fragment>
      ))}
    </dl>
  )
}

export function Checklist({ items, mark = '▸' }) {
  return (
    <ul className="checklist">
      {items.map((it, i) => (
        <li key={i}>
          <span className="mk">{typeof mark === 'function' ? mark(i) : mark}</span>
          <div>
            {typeof it === 'string' ? (
              <RichText text={it} />
            ) : (
              <>
                <b>{it.b}</b> <RichText text={it.t} />
              </>
            )}
          </div>
        </li>
      ))}
    </ul>
  )
}

export function Callout({ children }) {
  return <div className="callout">{children}</div>
}

export function OptionCard({ selected, title, desc, onClick }) {
  return (
    <button type="button" className={`opt ${selected ? 'sel' : ''}`} onClick={onClick}>
      <span className="tick" />
      <div>
        <div className="ot">{title}</div>
        {desc && <div className="od">{desc}</div>}
      </div>
    </button>
  )
}

export function Field({ label, hint, children }) {
  return (
    <div className="field">
      {label && <label>{label}</label>}
      {hint && <div className="hint">{hint}</div>}
      {children}
    </div>
  )
}

export function Stepmap({ labels, current }) {
  return (
    <div className="stepmap">
      {labels.map((l, i) => {
        const n = i + 1
        const cls = n < current ? 'done' : n === current ? 'active' : ''
        return (
          <span key={l} className={`chip ${cls}`}>
            <i>{String(n).padStart(2, '0')}</i>
            {l}
          </span>
        )
      })}
    </div>
  )
}
