import { lazy, Suspense, useEffect, useState } from 'react'
import { api } from './api'
import DataTable from './components/DataTable'

const GraphExplorer = lazy(() => import('./components/GraphExplorer'))

const tabs = [
  { id: 'rows', label: 'Raw rows' },
  { id: 'entities', label: 'Resolved entities' },
  { id: 'clean', label: 'Clean data' },
  { id: 'graph', label: 'Graph explorer' },
]

const views = {
  rows: { endpoint: '/rows', eyebrow: 'Source records', title: 'Raw relationship data', description: 'The original declarations, unchanged and fully traceable.' },
  entities: { endpoint: '/entities', eyebrow: 'Golden records', title: 'Resolved entities', description: 'Canonical companies after explainable matching and deduplication.' },
  clean: { endpoint: '/relationships/clean', eyebrow: 'Normalized records', title: 'Clean relationship data', description: 'Canonical IDs, normalized countries, tax IDs, dates, and categories.' },
}

function Logo() {
  return <div className="logo-mark" aria-hidden="true"><i /><i /><i /><span /></div>
}

function App() {
  const [active, setActive] = useState('rows')
  const [summary, setSummary] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api('/summary').then(setSummary).catch((err) => setError(err.message))
  }, [])

  const view = views[active]
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><Logo /><div><strong>SupplyScope</strong><small>Network intelligence</small></div></div>
        <nav aria-label="Data views">
          <p>Workspace</p>
          {tabs.map((tab) => (
            <button key={tab.id} className={active === tab.id ? 'active' : ''} onClick={() => setActive(tab.id)}>
              <span className={`nav-icon ${tab.id}`} aria-hidden="true" />{tab.label}
            </button>
          ))}
        </nav>
        <div className="dataset-card">
          <span className={`status-dot ${summary ? '' : 'loading'}`} />
          <div><small>Active dataset</small><strong>{summary?.source_file || 'Loading dataset…'}</strong></div>
        </div>
      </aside>

      <main>
        <header className="topbar">
          <div><span className="crumb">Supplier network</span><span className="slash">/</span><span>{tabs.find((t) => t.id === active)?.label}</span></div>
          <div className="profile"><span>AM</span><div><strong>Ahmed</strong><small>Data workspace</small></div></div>
        </header>

        <section className="content">
          {error && <div className="error-banner">Could not reach the API: {error}</div>}
          {active === 'graph' ? <Suspense fallback={<div className="graph-loading"><div className="spinner large" /><h2>Loading graph tools</h2></div>}><GraphExplorer summary={summary} /></Suspense> : (
            <>
              <div className="page-heading"><div><span className="eyebrow">{view.eyebrow}</span><h1>{view.title}</h1><p>{view.description}</p></div></div>
              {summary && <div className="stat-row">
                <Stat label="Rows processed" value={summary.rows} />
                <Stat label="Resolved entities" value={summary.entities} />
                <Stat label="Relationships" value={summary.relationships} />
                <Stat label="Needs review" value={summary.flagged_for_review} accent />
              </div>}
              <DataTable endpoint={view.endpoint} key={active} />
            </>
          )}
        </section>
      </main>
    </div>
  )
}

function Stat({ label, value, accent }) {
  return <div className="stat"><span className={accent ? 'stat-icon accent' : 'stat-icon'} /><div><strong>{value === null || value === undefined ? '—' : value.toLocaleString()}</strong><small>{label}</small></div></div>
}

export default App
