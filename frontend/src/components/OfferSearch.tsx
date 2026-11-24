import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import type { Offer } from '../types'

interface Props {
  onPick: (offer: Offer) => void
  exclude?: number[]
  placeholder?: string
  disabled?: boolean
  autoFocus?: boolean
}

/** Поиск оффера по ID или названию с автодополнением (запросы идут в API обёртки → Keitaro). */
export function OfferSearch({ onPick, exclude = [], placeholder, disabled, autoFocus }: Props) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<Offer[]>([])
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [highlight, setHighlight] = useState(0)
  const boxRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    let cancelled = false
    const timer = setTimeout(() => {
      setLoading(true)
      api
        .searchOffers(query)
        .then((offers) => {
          if (!cancelled) {
            setResults(offers.filter((o) => !exclude.includes(o.id)))
            setHighlight(0)
          }
        })
        .catch(() => !cancelled && setResults([]))
        .finally(() => !cancelled && setLoading(false))
    }, 200)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, open, exclude.join(',')])

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])

  const pick = (offer: Offer) => {
    onPick(offer)
    setQuery('')
    setOpen(false)
  }

  return (
    <div className="combo" ref={boxRef}>
      <input
        className="input"
        value={query}
        disabled={disabled}
        autoFocus={autoFocus}
        placeholder={placeholder ?? 'ID или название оффера'}
        onFocus={() => setOpen(true)}
        onChange={(e) => {
          setQuery(e.target.value)
          setOpen(true)
        }}
        onKeyDown={(e) => {
          if (e.key === 'ArrowDown') {
            e.preventDefault()
            setHighlight((h) => Math.min(h + 1, results.length - 1))
          } else if (e.key === 'ArrowUp') {
            e.preventDefault()
            setHighlight((h) => Math.max(h - 1, 0))
          } else if (e.key === 'Enter' && results[highlight]) {
            e.preventDefault()
            pick(results[highlight])
          } else if (e.key === 'Escape') {
            setOpen(false)
          }
        }}
        role="combobox"
        aria-expanded={open}
      />
      {open && (
        <ul className="combo-list" role="listbox">
          {loading && results.length === 0 && <li className="combo-empty">Ищу…</li>}
          {!loading && results.length === 0 && <li className="combo-empty">Ничего не найдено</li>}
          {results.map((offer, i) => (
            <li
              key={offer.id}
              role="option"
              aria-selected={i === highlight}
              className={i === highlight ? 'active' : ''}
              onMouseEnter={() => setHighlight(i)}
              onMouseDown={(e) => {
                e.preventDefault()
                pick(offer)
              }}
            >
              <span className="mono">{offer.id}</span> {offer.name.replace(new RegExp(`^${offer.id}\\s*`), '')}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
