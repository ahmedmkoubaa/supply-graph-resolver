import { useEffect, useRef, useState } from 'react'
import cytoscape from 'cytoscape'
import { api } from '../api'

const tierColors = ['#2563eb', '#0d9488', '#7c3aed', '#d97706', '#dc2626', '#475569']
const tierFills = ['#dbeafe', '#ccfbf1', '#ede9fe', '#fef3c7', '#fee2e2', '#e2e8f0']

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
      ...graph.nodes.map((node) => ({ data: { id: node.entity_id, label: node.canonical_name, tier: node.tier, country: node.country || '—', taxId: node.tax_id || '—', mentions: node.mention_count, ...(node.is_root ? { root: true } : {}) } })),
      ...graph.edges.map((edge, index) => ({ data: { id: `e${index}`, source: edge.source, target: edge.target, label: (edge.relationship_types || []).join(', ') || 'supplies' } })),
    ]
    graphInstance.current?.destroy()
    const cy = cytoscape({
      container: container.current,
      elements,
      style: [
        { selector: 'node', style: { 'background-color': (ele) => tierFills[Math.min(ele.data('tier'), tierFills.length - 1)], 'border-color': (ele) => tierColors[Math.min(ele.data('tier'), tierColors.length - 1)], label: 'data(label)', color: '#172033', 'font-size': 11, 'font-weight': 600, 'min-zoomed-font-size': 9, 'text-background-color': '#fff', 'text-background-opacity': 0.88, 'text-background-padding': 3, 'text-wrap': 'wrap', 'text-max-width': 120, 'text-valign': 'bottom', 'text-margin-y': 10, width: 34, height: 34, 'border-width': 6, 'shadow-blur': 12, 'shadow-opacity': 0.14, 'shadow-color': '#172033' } },
        { selector: 'node[root]', style: { width: 48, height: 48, 'background-color': '#172033', 'border-color': '#2563eb', 'border-width': 7, color: '#0f172a', 'font-size': 12 } },
        { selector: 'edge', style: { width: 1.25, 'line-color': '#b8c5d8', 'line-opacity': 0.22, 'target-arrow-color': '#94a3b8', 'target-arrow-shape': 'triangle', 'target-arrow-fill': 'filled', 'curve-style': 'bezier', 'arrow-scale': 0.7 } },
        { selector: ':selected', style: { 'overlay-color': '#2563eb', 'overlay-opacity': 0.12, 'overlay-padding': 8 } },
      ],
      layout: {
        name: 'concentric',
        animate: false,
        fit: false,
        minNodeSpacing: 85,
        spacingFactor: 1.45,
        concentric: (node) => -node.data('tier'),
        levelWidth: () => 1,
        startAngle: -Math.PI / 2,
        sweep: 2 * Math.PI,
        clockwise: true,
      },
      minZoom: 0.08,
      maxZoom: 2.5,
    })
    cy.on('tap', 'node', (event) => setFocusedNode(event.target.data()))
    const root = cy.nodes('[root]')
    cy.zoom(0.42)
    cy.center(root)
    graphInstance.current = cy
    return () => cy.destroy()
  }, [graph])

  function choose(entity) {
    setSelected(entity); setQuery(entity.canonical_name); setOptions([]); setFocusedNode(null); setGraph(null); setError(''); setLoading(true)
    api(`/entities/${entity.entity_id}/graph`).then(setGraph).catch((err) => setError(err.message)).finally(() => setLoading(false))
  }

  function fitGraph() {
    graphInstance.current?.fit(undefined, 60)
  }

  function centerRoot() {
    const cy = graphInstance.current
    if (!cy) return
    cy.zoom(0.42)
    cy.center(cy.nodes('[root]'))
  }

  function zoomBy(factor) {
    const cy = graphInstance.current
    if (!cy) return
    cy.zoom({ level: cy.zoom() * factor, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } })
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
          <div className="graph-toolbar"><div><strong>{selected.canonical_name}</strong><span>{graph.nodes.length} entities · {graph.edges.length} relationships</span></div><div className="legend">{[...new Set(graph.nodes.map((n) => n.tier))].sort().map((tier) => <span key={tier}><i style={{ borderColor: tierColors[Math.min(tier, tierColors.length - 1)], background: tierFills[Math.min(tier, tierFills.length - 1)] }} />Tier {tier}</span>)}</div></div>
          <div ref={container} className="graph-canvas" />
          <div className="graph-controls" aria-label="Graph view controls"><button onClick={() => zoomBy(1.25)} aria-label="Zoom in">+</button><button onClick={() => zoomBy(0.8)} aria-label="Zoom out">−</button><button onClick={centerRoot}>Center root</button><button onClick={fitGraph}>Fit all</button></div>
          <div className="canvas-help">Scroll to zoom · Drag to pan · Select a node for details</div>
        </div>
        <aside className="detail-panel">
          {focusedNode ? <><span className="tier-badge">Tier {focusedNode.tier}</span><h2>{focusedNode.label}</h2><dl><div><dt>Entity ID</dt><dd>{focusedNode.id}</dd></div><div><dt>Country</dt><dd>{focusedNode.country}</dd></div><div><dt>Tax ID</dt><dd>{focusedNode.taxId}</dd></div><div><dt>Source mentions</dt><dd>{focusedNode.mentions}</dd></div></dl></> : <><span className="detail-symbol">↖</span><h2>Entity details</h2><p>Select a node in the graph to inspect its canonical identity and source coverage.</p></>}
        </aside>
      </div>}
    </>
  )
}
