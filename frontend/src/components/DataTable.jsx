import { useEffect, useState } from 'react'
import { api } from '../api'

const PAGE_SIZE = 25

function display(value) {
  if (value === null || value === undefined || value === '') return <span className="empty">—</span>
  if (Array.isArray(value)) return value.join(' · ')
  return String(value)
}

export default function DataTable({ endpoint }) {
  const [page, setPage] = useState(0)
  const [query, setQuery] = useState('')
  const [data, setData] = useState({ items: [], total: 0 })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    const timer = setTimeout(() => {
      setLoading(true)
      setError('')
      api(endpoint, { offset: page * PAGE_SIZE, limit: PAGE_SIZE, query })
        .then(setData)
        .catch((err) => setError(err.message))
        .finally(() => setLoading(false))
    }, query ? 250 : 0)
    return () => clearTimeout(timer)
  }, [endpoint, page, query])

  const columns = data.items[0] ? Object.keys(data.items[0]) : []
  const first = data.total ? page * PAGE_SIZE + 1 : 0
  const last = Math.min((page + 1) * PAGE_SIZE, data.total)

  return (
    <div className="table-card">
      <div className="table-toolbar">
        <label className="search-box"><span aria-hidden="true" /><input value={query} onChange={(event) => { setQuery(event.target.value); setPage(0) }} placeholder="Search across all columns…" aria-label="Search table" /></label>
        <span className="result-count">{data.total.toLocaleString()} records</span>
      </div>
      <div className="table-wrap">
        {loading && <div className="loading-layer"><div className="spinner" /><span>Loading records…</span></div>}
        {error ? <div className="empty-state">{error}</div> : !loading && !data.items.length ? <div className="empty-state">No records match your search.</div> : (
          <table>
            <thead><tr>{columns.map((column) => <th key={column}>{column.replaceAll('_', ' ')}</th>)}</tr></thead>
            <tbody>{data.items.map((row, index) => <tr key={row.row_id || row.entity_id || index}>{columns.map((column) => <td key={column} title={Array.isArray(row[column]) ? row[column].join(' · ') : row[column] || ''}>{display(row[column])}</td>)}</tr>)}</tbody>
          </table>
        )}
      </div>
      <div className="pagination"><span>Showing {first}–{last} of {data.total.toLocaleString()}</span><div><button onClick={() => setPage((p) => p - 1)} disabled={page === 0 || loading}>Previous</button><span>Page {page + 1}</span><button onClick={() => setPage((p) => p + 1)} disabled={last >= data.total || loading}>Next</button></div></div>
    </div>
  )
}
