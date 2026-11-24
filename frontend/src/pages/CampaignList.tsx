import { useEffect, useState } from 'react'
import { api, ApiError } from '../api'
import { useToast } from '../components/toast-context'
import type { KtCampaign } from '../types'

export function CampaignList({ prefix }: { prefix: string }) {
  const toast = useToast()
  const [items, setItems] = useState<KtCampaign[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<number | null>(null)
  const [manualId, setManualId] = useState('')

  const load = () =>
    api.keitaroCampaigns().then(setItems).catch((e) => setError(e instanceof ApiError ? e.message : String(e)))
  useEffect(() => { load() }, [])

  const open = async (ktId: number) => {
    setBusyId(ktId)
    try {
      const campaign = await api.importCampaign(ktId)
      window.location.hash = `#/campaigns/${campaign.id}`
    } catch (e) {
      toast(e instanceof ApiError ? e.message : String(e), 'error')
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="card">
      <div className="row between">
        <h2>Кампании в Keitaro</h2>
        <div className="row gap">
          <button className="btn ghost" onClick={load}>Обновить</button>
          <a className="btn primary" href="#/new">+ Новая кампания</a>
        </div>
      </div>
      {error && <div className="alert error">{error}</div>}
      {items === null && !error && <p className="muted">Загрузка…</p>}
      {items?.length === 0 && <p className="muted">В аккаунте пока нет кампаний — создайте первую.</p>}
      {items && items.length > 0 && (
        <table className="table">
          <thead>
            <tr><th>ID</th><th>Название</th><th>Домен</th><th>Группа</th><th /></tr>
          </thead>
          <tbody>
            {items.map((c) => (
              <tr key={c.kt_id}>
                <td className="mono">{c.kt_id}</td>
                <td>
                  {c.name}
                  {prefix && !c.name.startsWith(prefix) && <span className="tag">только чтение</span>}
                </td>
                <td>{c.domain ?? '—'}</td>
                <td>{c.group ?? '—'}</td>
                <td className="right">
                  <button className="btn small" disabled={busyId === c.kt_id} onClick={() => open(c.kt_id)}>
                    {busyId === c.kt_id ? 'Загрузка…' : c.local_id ? 'Открыть' : 'Подключить'}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <form className="row gap top-gap" onSubmit={(e) => { e.preventDefault(); if (Number(manualId) > 0) open(Number(manualId)) }}>
        <input className="input narrow-input" value={manualId} onChange={(e) => setManualId(e.target.value.replace(/\D/g, ''))} placeholder="ID кампании Keitaro" />
        <button className="btn" disabled={!manualId}>Подключить по ID</button>
      </form>
    </div>
  )
}
