import { useEffect, useState } from 'react'
import { api, ApiError } from './api'
import { CampaignList } from './pages/CampaignList'
import { Creator } from './pages/Creator'
import { Editor } from './pages/Editor'
import type { Meta } from './types'

function useHashRoute(): string[] {
  const parse = () => window.location.hash.replace(/^#\/?/, '').split('/').filter(Boolean)
  const [route, setRoute] = useState(parse)
  useEffect(() => {
    const onChange = () => setRoute(parse())
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  return route
}

export default function App() {
  const route = useHashRoute()
  const [meta, setMeta] = useState<Meta | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.meta().then(setMeta).catch((e) => setError(e instanceof ApiError ? e.message : String(e)))
  }, [])

  const page = route[0] ?? ''
  return (
    <>
      <header className="topbar">
        <a className="brand" href="#/">Keitaro<span>Wrapper</span></a>
        <nav>
          <a className={page === '' || page === 'campaigns' ? 'active' : ''} href="#/">Кампании</a>
          <a className={page === 'new' ? 'active' : ''} href="#/new">Создать кампанию</a>
        </nav>
      </header>
      <main className="container">
        {error && <div className="card"><div className="alert error">Не удалось загрузить справочники Keitaro: {error}</div></div>}
        {!meta && !error && <div className="card muted">Загрузка…</div>}
        {meta && page === 'new' && <Creator meta={meta} />}
        {meta && page === 'campaigns' && route[1] && <Editor key={route[1]} campaignId={Number(route[1])} />}
        {meta && (page === '' || (page === 'campaigns' && !route[1])) && <CampaignList prefix={meta.write_allowed_prefix} />}
      </main>
    </>
  )
}
