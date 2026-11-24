import { useCallback, useEffect, useState } from 'react'
import { api, ApiError } from '../api'
import { PinIcon } from '../components/icons'
import { OfferSearch } from '../components/OfferSearch'
import { useToast } from '../components/toast-context'
import type { Campaign, Stream, StreamOffer } from '../types'

const errorText = (e: unknown) => (e instanceof ApiError ? e.message : String(e))

export function Editor({ campaignId }: { campaignId: number }) {
  const toast = useToast()
  const [campaign, setCampaign] = useState<Campaign | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [fetching, setFetching] = useState(false)
  const [showArchived, setShowArchived] = useState(true)

  useEffect(() => {
    api.campaign(campaignId).then(setCampaign).catch((e) => setError(errorText(e)))
  }, [campaignId])

  const replaceStream = useCallback((stream: Stream) => {
    setCampaign((c) => (c ? { ...c, streams: c.streams.map((s) => (s.id === stream.id ? stream : s)) } : c))
  }, [])

  const fetchFromKt = async () => {
    if (campaign?.streams.some((s) => s.is_dirty) &&
        !window.confirm('Есть неопубликованные изменения. FETCH заменит их тем, что сейчас в Keitaro. Продолжить?')) {
      return
    }
    setFetching(true)
    try {
      setCampaign(await api.fetchCampaign(campaignId))
      toast('Потоки загружены из Keitaro', 'ok')
    } catch (e) {
      toast(errorText(e), 'error')
    } finally {
      setFetching(false)
    }
  }

  if (error) return <div className="card"><div className="alert error">{error}</div></div>
  if (!campaign) return <div className="card"><p className="muted">Загрузка…</p></div>

  const dirtyCount = campaign.streams.filter((s) => s.is_dirty).length

  return (
    <div>
      <div className="card campaign-head">
        <div>
          <div className="crumbs"><a href="#/">Кампании</a> / {campaign.name}</div>
          <h2>{campaign.name}</h2>
          <div className="meta-line">
            <span>Keitaro ID <b className="mono">{campaign.kt_id}</b></span>
            <span>Домен <b>{campaign.domain ?? '—'}</b></span>
            <span>Группа <b>{campaign.group_name ?? '—'}</b></span>
            {campaign.last_fetched_at && <span>Синхронизировано {new Date(campaign.last_fetched_at).toLocaleString('ru-RU')}</span>}
          </div>
          {!campaign.writable && (
            <div className="alert warn">Кампания не из ваших тестовых (нет префикса) — редактировать можно, публиковать нельзя.</div>
          )}
        </div>
        <div className="toolbar">
          <button className="btn" onClick={fetchFromKt} disabled={fetching}>
            {fetching ? 'Загрузка…' : 'FETCH STREAMS FROM KT ⤓'}
          </button>
          <a className="btn" href={campaign.keitaro_url} target="_blank" rel="noreferrer">VIEW IN KT ↗</a>
          <button className="btn ghost" onClick={() => setShowArchived((v) => !v)}>
            {showArchived ? 'HIDE ARCHIVED' : 'SHOW ALL OFFERS'}
          </button>
          {dirtyCount > 1 && (
            <PushAllButton campaign={campaign} onDone={setCampaign} />
          )}
        </div>
      </div>

      {campaign.streams.length === 0 && <div className="card muted">В кампании нет потоков.</div>}
      {campaign.streams.map((stream) => (
        <StreamCard
          key={stream.id}
          stream={stream}
          writable={campaign.writable}
          showArchived={showArchived}
          onChange={replaceStream}
          onRefetch={fetchFromKt}
        />
      ))}
    </div>
  )
}

function PushAllButton({ campaign, onDone }: { campaign: Campaign; onDone: (c: Campaign) => void }) {
  const toast = useToast()
  const [busy, setBusy] = useState(false)
  return (
    <button
      className="btn primary"
      disabled={busy || !campaign.writable}
      onClick={async () => {
        setBusy(true)
        try {
          const res = await api.pushCampaign(campaign.id)
          onDone(res.campaign)
          toast(`Опубликовано потоков: ${res.results.length}`, 'ok')
        } catch (e) {
          toast(errorText(e), 'error')
        } finally {
          setBusy(false)
        }
      }}
    >
      PUSH ALL TO KT
    </button>
  )
}

interface CardProps {
  stream: Stream
  writable: boolean
  showArchived: boolean
  onChange: (s: Stream) => void
  onRefetch: () => void
}

function StreamCard({ stream, writable, showArchived, onChange, onRefetch }: CardProps) {
  const toast = useToast()
  const [busy, setBusy] = useState(false)
  const [conflict, setConflict] = useState<string | null>(null)

  const run = async (action: () => Promise<Stream>) => {
    setBusy(true)
    try {
      onChange(await action())
    } catch (e) {
      toast(errorText(e), 'error')
    } finally {
      setBusy(false)
    }
  }

  const push = async (force = false) => {
    setBusy(true)
    try {
      const res = await api.push(stream.id, force)
      onChange(res.stream)
      setConflict(null)
      toast(res.result.message, 'ok')
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) setConflict(e.message)
      else toast(errorText(e), 'error')
    } finally {
      setBusy(false)
    }
  }

  const visible = stream.offers.filter((o) => showArchived || o.status === 'active')
  const archivedHidden = stream.offers.length - visible.length
  const canPush = writable && stream.issues.length === 0

  return (
    <section className={`card stream ${stream.is_dirty ? 'dirty' : ''}`} aria-busy={busy}>
      <header className="stream-head">
        <div>
          <h3>
            Stream: {stream.name} <span className="muted">(#{stream.position})</span>
          </h3>
          <div className="muted small">
            stream_id {stream.kt_id} · {stream.type ?? '—'} / {stream.schema ?? '—'}
            {stream.offers.length > 0 && <> · активных долей: <b className={stream.active_share_sum === 100 ? '' : 'error-text'}>{stream.active_share_sum}%</b></>}
          </div>
        </div>
        {stream.is_dirty && (
          <div className="row gap">
            <span className="tag tag-warn">не опубликовано</span>
            <button className="btn primary" disabled={busy || !canPush} onClick={() => push()} title={canPush ? '' : 'Исправьте доли перед публикацией'}>
              ⤒ PUSH TO KT
            </button>
            <button className="btn" disabled={busy} onClick={() => run(() => api.cancel(stream.id))}>✕ CANCEL</button>
          </div>
        )}
      </header>

      {conflict && (
        <div className="alert warn">
          {conflict}
          <div className="row gap top-gap">
            <button className="btn small" onClick={() => { setConflict(null); onRefetch() }}>FETCH STREAMS FROM KT</button>
            <button className="btn small danger" onClick={() => push(true)}>Опубликовать всё равно</button>
          </div>
        </div>
      )}

      {stream.issues.map((issue) => (
        <div key={issue.code} className="alert error row between">
          <span>{issue.message}</span>
          {(issue.code === 'sum_not_100' || issue.code === 'not_enough_for_unpinned') && (
            <button className="btn small" disabled={busy} onClick={() => run(() => api.rebalance(stream.id))}>Выровнять</button>
          )}
        </div>
      ))}

      {!stream.accepts_offers ? (
        <p className="muted empty-stream">Поток без офферов. Его фильтры и редирект обёртка не разбирает — для редактора офферов они не важны.</p>
      ) : (
        <>
          <table className="table offers">
            <thead>
              <tr><th>Оффер</th><th className="share-col">Share</th><th>Статус</th><th className="right">Actions</th></tr>
            </thead>
            <tbody>
              {visible.map((offer) => (
                <OfferRow key={offer.id} stream={stream} offer={offer} busy={busy} run={run} />
              ))}
              {visible.length === 0 && (
                <tr><td colSpan={4} className="muted">Офферов нет — добавьте первый ниже.</td></tr>
              )}
            </tbody>
          </table>
          {archivedHidden > 0 && <p className="muted small">Скрыто архивных офферов: {archivedHidden}</p>}
          <AddOffer stream={stream} busy={busy} run={run} />
        </>
      )}
    </section>
  )
}

const BADGES: Record<StreamOffer['badge'], [string, string]> = {
  active: ['в Keitaro', 'tag-ok'],
  new: ['новый', 'tag-warn'],
  removed_pending: ['будет удалён', 'tag-warn'],
  restored_pending: ['будет возвращён', 'tag-warn'],
  archived: ['архив', ''],
}

function OfferRow({ stream, offer, busy, run }: {
  stream: Stream
  offer: StreamOffer
  busy: boolean
  run: (a: () => Promise<Stream>) => Promise<void>
}) {
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState(String(offer.share))
  const active = offer.status === 'active'
  const [label, cls] = BADGES[offer.badge]
  const changedShare = active && offer.published_status === 'active' && offer.published_share !== offer.share

  const saveShare = () => {
    const share = Number(value)
    setEditing(false)
    if (share >= 1 && share <= 100 && share !== offer.share) {
      run(() => api.updateOffer(stream.id, offer.id, { share }))
    }
  }

  return (
    <tr className={active ? '' : 'archived'}>
      <td>
        <div className="offer-name">{offer.offer_name}</div>
        {!active && <div className="muted small">(removed)</div>}
      </td>
      <td className="share-col">
        <div className="share">
          {editing ? (
            <input
              className="input share-input"
              type="number"
              min={1}
              max={100}
              autoFocus
              value={value}
              onChange={(e) => setValue(e.target.value)}
              onBlur={saveShare}
              onKeyDown={(e) => { if (e.key === 'Enter') saveShare(); if (e.key === 'Escape') setEditing(false) }}
            />
          ) : (
            <button
              className="link share-value"
              disabled={!active || busy}
              title={active ? 'Задать долю вручную (оффер закрепится)' : ''}
              onClick={() => { setValue(String(offer.share)); setEditing(true) }}
            >
              {offer.share}%
            </button>
          )}
          <button
            className={`pin ${offer.pinned ? 'on' : ''}`}
            disabled={!active || busy}
            title={offer.pinned ? 'Открепить долю' : 'Закрепить долю'}
            aria-label={offer.pinned ? 'Открепить долю' : 'Закрепить долю'}
            onClick={() => run(() => api.updateOffer(stream.id, offer.id, { pinned: !offer.pinned }))}
          >
            <PinIcon filled={offer.pinned} />
          </button>
        </div>
        {changedShare && <div className="muted small">в KT: {offer.published_share}%</div>}
      </td>
      <td><span className={`tag ${cls}`}>{label}</span></td>
      <td className="right">
        {active ? (
          <button className="btn small" disabled={busy} onClick={() => run(() => api.removeOffer(stream.id, offer.id))}>🗑 REMOVE</button>
        ) : (
          <button className="btn small" disabled={busy} onClick={() => run(() => api.restoreOffer(stream.id, offer.id))}>↺ BRING BACK</button>
        )}
      </td>
    </tr>
  )
}

function AddOffer({ stream, busy, run }: {
  stream: Stream
  busy: boolean
  run: (a: () => Promise<Stream>) => Promise<void>
}) {
  const [picked, setPicked] = useState<{ id: number; name: string } | null>(null)
  const exclude = stream.offers.filter((o) => o.status === 'active').map((o) => o.offer_id)
  return (
    <div className="add-offer">
      {picked ? (
        <div className="picked-offer">
          <span>{picked.name}</span>
          <button className="link" onClick={() => setPicked(null)}>изменить</button>
        </div>
      ) : (
        <OfferSearch onPick={setPicked} exclude={exclude} disabled={busy} />
      )}
      <button
        className="btn primary"
        disabled={!picked || busy}
        onClick={() => picked && run(() => api.addOffer(stream.id, picked.id)).then(() => setPicked(null))}
      >
        ADD
      </button>
    </div>
  )
}
