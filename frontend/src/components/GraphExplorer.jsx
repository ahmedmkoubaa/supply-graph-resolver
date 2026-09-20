import { useEffect, useRef, useState } from 'react'
import cytoscape from 'cytoscape'
import { api } from '../api'

const tierColors = ['#2563eb', '#0d9488', '#7c3aed', '#d97706', '#dc2626', '#475569']

export default function GraphExplorer({ summary }) {
  const container = useRef(null)
  const graphInstance = useRef(null)
  const [query, setQuery] = useState('')
  const [options, setOptions] = useState([])
  const [selected, setSelected] = useState(null)
  const [graph, setGraph] = useState(null)
  const [focusedNode, setFocusedNode] = useState(null)
  const [searching, setSearching] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (query.trim().length < 2 || selected?.canonical_name === query) return
    const timer = setTimeout(() => {
      setSearching(true)
      api('/entities', { query, limit: 8 }).then((result) => setOptions(result.items)).catch((err) => setError(err.message)).finally(() => setSearching(false))
    }, 250)
    return () => clearTimeout(timer)
  }, [query, selected])

  useEffect(() => {
    if (!graph || !container.current) return
    const elements = [
      ...graph.nodes.map((node) => ({ data: { id: node.entity_id, label: node.canonical_name, tier: node.tier, country: node.country || '—', taxId: node.tax_id || '—', mentions: node.mention_count, root: node.is_root } })),
      ...graph.edges.map((edge, index) => ({ data: { id: `e${index}`, source: edge.source, target: edge.target, label: (edge.relationship_types || []).join(', ') || 'supplies' } })),
    ]
    graphInstance.current?.destroy()
    const cy = cytoscape({
      container: container.current,
      elements,
      style: [
        { selector: 'node', style: { 'background-color': (ele) => tierColors[Math.min(ele.data('tier'), tierColors.length - 1)], label: 'data(label)', color: '#172033', 'font-size': 10, 'font-weight': 600, 'text-wrap': 'wrap', 'text-max-width': 100, 'text-valign': 'bottom', 'text-margin-y': 8, width: 30, height: 30, 'border-width': 4, 'border-color': '#fff', 'shadow-blur': 12, 'shadow-opacity': 0.16, 'shadow-color': '#172033' } },
        { selector: 'node[root]', style: { width: 42, height: 42, 'background-color': '#172033', 'border-color': '#93c5fd', 'border-width': 5 } },
        { selector: 'edge', style: { width: 1.5, 'line-color': '#cbd5e1', 'target-arrow-color': '#94a3b8', 'target-arrow-shape': 'triangle', 'curve-style': 'bezier', 'arrow-scale': 0.8 } },
        { selector: ':selected', style: { 'overlay-color': '#2563eb', 'overlay-opacity': 0.12, 'overlay-padding': 8 } },
      ],
      layout: { name: 'cose', animate: false, nodeRepulsion: 9000, idealEdgeLength: 110, gravity: 0.25, componentSpacing: 80 },
      minZoom: 0.2,
      maxZoom: 2.5,
    })
    cy.on('tap', 'node', (event) => setFocusedNode(event.target.data()))
    graphInstance.current = cy
    return () => cy.destroy()
  }, [graph])

  function choose(entity) {
    setSelected(entity); setQuery(entity.canonical_name); setOptions([]); setFocusedNode(null); setGraph(null); setError(''); setLoading(true)
    api(`/entities/${entity.entity_id}/graph`).then(setGraph).catch((err) => setError(err.message)).finally(() => setLoading(false))
  }

  return (
    <>
      <div className="graph-heading">
        <div><span className="eyebrow">Network intelligence</span><h1>Explore supplier tiers</h1><p>Choose any resolved entity to map its complete upstream supply chain.</p></div>
        <div className="graph-search">
          <label><span className="search-icon" /><input value={query} onChange={(event) => { setQuery(event.target.value); setSelected(null); setOptions([]) }} placeholder="Search an entity…" aria-label="Search an entity" />{searching && <i className="mini-spinner" />}</label>
          {options.length > 0 && <div className="search-results">{options.map((entity) => <button key={entity.entity_id} onClick={() => choose(entity)}><span>{entity.canonical_name}<small>{entity.entity_id} · {entity.country || 'Unknown country'}</small></span><b>View graph</b></button>)}</div>}
        </div>
      </div>

      {!selected && !loading && <div className="graph-welcome"><div className="network-orbit"><span /><i /><i /><i /><i /></div><h2>Start with a company</h2><p>Search from {summary?.entities?.toLocaleString() || 'the'} resolved entities. We’ll trace every available supplier tier.</p></div>}
      {loading && <div className="graph-loading"><div className="spinner large" /><h2>Building the supply chain</h2><p>Traversing upstream relationships and assigning tiers…</p></div>}
      {error && <div className="error-banner">{error}</div>}
      {graph && <div className="graph-layout">
        <div className="graph-canvas-card">
          <div className="graph-toolbar"><div><strong>{selected.canonical_name}</strong><span>{graph.nodes.length} entities · {graph.edges.length} relationships</span></div><div className="legend">{[...new Set(graph.nodes.map((n) => n.tier))].sort().map((tier) => <span key={tier}><i style={{ background: tierColors[Math.min(tier, tierColors.length - 1)] }} />Tier {tier}</span>)}</div></div>
          <div ref={container} className="graph-canvas" />
          <div className="canvas-help">Scroll to zoom · Drag to pan · Select a node for details</div>
        </div>
        <aside className="detail-panel">
          {focusedNode ? <><span className="tier-badge">Tier {focusedNode.tier}</span><h2>{focusedNode.label}</h2><dl><div><dt>Entity ID</dt><dd>{focusedNode.id}</dd></div><div><dt>Country</dt><dd>{focusedNode.country}</dd></div><div><dt>Tax ID</dt><dd>{focusedNode.taxId}</dd></div><div><dt>Source mentions</dt><dd>{focusedNode.mentions}</dd></div></dl></> : <><span className="detail-symbol">↖</span><h2>Entity details</h2><p>Select a node in the graph to inspect its canonical identity and source coverage.</p></>}
        </aside>
      </div>}
    </>
  )
}
