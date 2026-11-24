import { useMemo, useState } from 'react'
import { api, ApiError } from '../api'
import { OfferSearch } from '../components/OfferSearch'
import { useToast } from '../components/toast-context'
import type { Campaign, Meta, Offer } from '../types'

const splitGeo = (raw: string) =>
  [...new Set(raw.split(/[\s,;]+/).map((c) => c.trim().toUpperCase()).filter(Boolean))]

export function Creator({ meta }: { meta: Meta }) {
  const toast = useToast()
  const prefix = meta.campaign_name_prefix
  const [name, setName] = useState('')
  const [geo, setGeo] = useState('')
  const [offers, setOffers] = useState<Offer[]>([])
  const [domainId, setDomainId] = useState<number | null>(meta.defaults.domain_id)
  const [groupId, setGroupId] = useState<number | null>(meta.defaults.group_id)
  const [sourceId, setSourceId] = useState<number | null>(meta.defaults.traffic_source_id)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [created, setCreated] = useState<Campaign | null>(null)

  const codes = useMemo(() => splitGeo(geo), [geo])
  const invalid = codes.filter((c) => !meta.countries[c])
  const fullName = name.trim().startsWith(prefix) ? name.trim() : prefix + name.trim()
  const canSubmit = name.trim() && codes.length > 0 && invalid.length === 0 && offers.length > 0 && !busy

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!canSubmit) return
    setBusy(true)
    try {
      const campaign = await api.createCampaign({
        name: name.trim(),
        geo: codes.join(','),
        offer_ids: offers.map((o) => o.id),
        domain_id: domainId,
        group_id: groupId,
        traffic_source_id: sourceId,
      })
      setCreated(campaign)
      toast(`Кампания «${campaign.name}» создана в Keitaro`, 'ok')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  if (created) {
    const [geoStream, offerStream] = created.streams
    return (
      <div className="card narrow">
        <h2>Готово ✅</h2>
        <p>
          Кампания <b>{created.name}</b> (ID {created.kt_id}) создана в Keitaro и подключена к редактору.
        </p>
        <ol className="summary">
          <li>
            <b>{geoStream?.name}</b> — посетители из {codes.join(', ')} → редирект на Google
          </li>
          <li>
            <b>{offerStream?.name}</b> — все остальные →{' '}
            {offerStream?.offers.map((o) => `${o.offer_name} (${o.share}%)`).join(', ')}
          </li>
        </ol>
        <p className="muted">
          Домен {created.domain ?? '—'}, группа {created.group_name ?? '—'}, ротация потоков по позиции.
        </p>
        <div className="row gap">
          <a className="btn primary" href={`#/campaigns/${created.id}`}>Открыть в редакторе</a>
          <a className="btn" href={created.keitaro_url} target="_blank" rel="noreferrer">VIEW IN KT ↗</a>
          <button className="btn ghost" onClick={() => { setCreated(null); setName(''); setGeo(''); setOffers([]) }}>
            Создать ещё
          </button>
        </div>
      </div>
    )
  }

  return (
    <form className="card narrow" onSubmit={submit}>
      <h2>Новая кампания</h2>
      <p className="muted">
        Создаются два потока: посетители из выбранных стран уходят на Google, все остальные — на оффер.
      </p>

      <label className="field">
        <span>Name</span>
        <div className="input-group">
          <span className="addon">{prefix}</span>
          <input
            className="input"
            value={name.startsWith(prefix) ? name.slice(prefix.length) : name}
            onChange={(e) => { setName(e.target.value); setError(null) }}
            placeholder="имя кампании"
            maxLength={200}
            autoFocus
          />
        </div>
        {name.trim() && <small className="muted">В Keitaro: {fullName}</small>}
      </label>

      <label className="field">
        <span>Geo</span>
        <input
          className={`input ${invalid.length ? 'invalid' : ''}`}
          value={geo}
          onChange={(e) => { setGeo(e.target.value); setError(null) }}
          placeholder="MX,AU,RO,..."
        />
        <div className="chips">
          {codes.map((c) => (
            <span key={c} className={`chip ${meta.countries[c] ? '' : 'chip-bad'}`} title={meta.countries[c] ?? 'Нет такого кода ISO 3166-1'}>
              {c} {meta.countries[c] ? `· ${meta.countries[c]}` : '· ?'}
            </span>
          ))}
        </div>
        {invalid.length > 0 && <small className="error-text">Неизвестные коды: {invalid.join(', ')} (нужен ISO-2, например GB, а не UK)</small>}
      </label>

      <div className="field">
        <span>Offer</span>
        <OfferSearch onPick={(o) => { setOffers((list) => [...list, o]); setError(null) }} exclude={offers.map((o) => o.id)} placeholder="поиск по офферам: ID или название" />
        {offers.length > 0 && (
          <ul className="picked">
            {offers.map((o, i) => (
              <li key={o.id}>
                <span>{o.name}</span>
                <span className="muted">{Math.floor(100 / offers.length) + (i < 100 % offers.length ? 1 : 0)}%</span>
                <button type="button" className="link danger" onClick={() => setOffers((l) => l.filter((x) => x.id !== o.id))}>убрать</button>
              </li>
            ))}
          </ul>
        )}
        <small className="muted">Можно выбрать несколько — доли разделятся поровну.</small>
      </div>

      <details className="field">
        <summary>Настройки кампании (домен, группа, источник)</summary>
        <div className="grid3">
          <Select label="Домен" items={meta.domains} value={domainId} onChange={setDomainId} />
          <Select label="Группа" items={meta.groups} value={groupId} onChange={setGroupId} />
          <Select label="Источник" items={meta.traffic_sources} value={sourceId} onChange={setSourceId} />
        </div>
      </details>

      {error && <div className="alert error">{error}</div>}
      <button className="btn primary wide" disabled={!canSubmit}>
        {busy ? 'Создаю…' : 'Create'}
      </button>
    </form>
  )
}

function Select({ label, items, value, onChange }: {
  label: string
  items: { id: number; name: string }[]
  value: number | null
  onChange: (v: number | null) => void
}) {
  return (
    <label className="field small">
      <span>{label}</span>
      <select className="input" value={value ?? ''} onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}>
        {items.map((i) => (
          <option key={i.id} value={i.id}>{i.name}</option>
        ))}
      </select>
    </label>
  )
}
