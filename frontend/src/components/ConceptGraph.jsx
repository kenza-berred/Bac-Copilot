/** Prerequisite graph: one column per chapter, concepts ordered by depth, arrows = "is a prerequisite of". */
export default function ConceptGraph({ graph, mastery }) {
  const chapters = Object.keys(graph.chapters);
  const W = 560, colW = W / chapters.length, rowH = 62, boxW = colW - 16, boxH = 42;
  const pos = {};
  chapters.forEach((ch, ci) => {
    graph.nodes.filter((n) => n.chapter === ch).forEach((n, ri) => {
      pos[n.id] = { x: ci * colW + 8, y: ri * rowH + 8 };
    });
  });
  const H = Math.max(...Object.values(pos).map((p) => p.y)) + boxH + 16;

  const color = (id) => {
    const m = mastery?.[id];
    if (!m || !m.n_attempts) return "var(--unseen)";
    return m.p_know >= 0.8 ? "var(--good)" : m.p_know >= 0.55 ? "var(--mid)" : "var(--bad)";
  };

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="cgraph" role="img" aria-label="Graphe des prérequis">
      <defs>
        <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M0,0 L10,5 L0,10 z" fill="var(--muted)" />
        </marker>
      </defs>
      {graph.edges.map((e) => {
        const a = pos[e.from], b = pos[e.to];
        const x1 = a.x + boxW / 2, y1 = a.y + boxH, x2 = b.x + boxW / 2, y2 = b.y;
        const path = a.x === b.x
          ? `M${x1},${y1} L${x2},${y2 - 2}`
          : `M${a.x + boxW},${a.y + boxH / 2} C${a.x + boxW + 30},${a.y + boxH / 2} ${b.x - 30},${b.y + boxH / 2} ${b.x - 2},${b.y + boxH / 2}`;
        return <path key={`${e.from}-${e.to}`} d={path} fill="none" stroke="var(--muted)" strokeWidth="1.2" markerEnd="url(#arrow)" opacity="0.7" />;
      })}
      {graph.nodes.map((n) => (
        <g key={n.id} transform={`translate(${pos[n.id].x},${pos[n.id].y})`}>
          <rect width={boxW} height={boxH} rx="8" fill="var(--card)" stroke={color(n.id)} strokeWidth="2.5" />
          <foreignObject width={boxW} height={boxH}>
            <div className="cnode">{n.label}</div>
          </foreignObject>
        </g>
      ))}
    </svg>
  );
}
