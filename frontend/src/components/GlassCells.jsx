import { useEffect, useRef } from "react";

/**
 * The hero visual: cells seen under a microscope, rendered as glass.
 * - a large cell with a blue nucleus (chromatin speckles),
 * - two dividing cells whose asters radiate spindle fibres,
 * - tilted glass lenses / slides,
 * - fine spindle fibres linking the dividing cells.
 * Pure CSS + one SVG. The pointer moves the layers slightly (parallax by depth).
 */
const ITEMS = [
  { kind: "lens", x: 33, y: 50, size: 300, depth: 0.6, tilt: 62, rot: -24 },
  { kind: "cell", x: 52, y: 55, size: 230, depth: 1.0 },
  { kind: "aster", x: 45, y: 20, size: 92, depth: 1.4 },
  { kind: "lens", x: 64, y: 36, size: 250, depth: 0.8, tilt: 58, rot: 12 },
  { kind: "bubble", x: 58, y: 30, size: 40, depth: 1.6 },
  { kind: "aster", x: 82, y: 56, size: 128, depth: 1.2 },
  { kind: "lens", x: 88, y: 46, size: 110, depth: 1.1, tilt: 40, rot: 8 },
  { kind: "bubble", x: 38, y: 12, size: 34, depth: 0.5 },
  { kind: "lens", x: 57, y: 76, size: 120, depth: 1.3, tilt: 20, rot: 0, filled: true },
];

export default function GlassCells({ focus = 0 }) {
  const stage = useRef(null);

  useEffect(() => {
    const el = stage.current;
    if (!el || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return undefined;
    const move = (e) => {
      const r = el.getBoundingClientRect();
      el.style.setProperty("--px", ((e.clientX - r.left) / r.width - 0.5).toFixed(3));
      el.style.setProperty("--py", ((e.clientY - r.top) / r.height - 0.5).toFixed(3));
    };
    window.addEventListener("pointermove", move);
    return () => window.removeEventListener("pointermove", move);
  }, []);

  return (
    <div className="cells" ref={stage} data-focus={focus} aria-hidden="true">
      <div className="prism" />
      <svg className="fibres" viewBox="0 0 100 100" preserveAspectRatio="none">
        <line x1="45" y1="20" x2="52" y2="55" />
        <line x1="45" y1="20" x2="58" y2="30" />
        <line x1="52" y1="55" x2="82" y2="56" />
        <line x1="82" y1="56" x2="88" y2="46" />
        <line x1="38" y1="12" x2="45" y2="20" />
      </svg>
      {ITEMS.map((it, i) => (
        <div
          key={i}
          className={`g g-${it.kind} ${it.filled ? "filled" : ""}`}
          style={{
            "--x": `${it.x}%`, "--y": `${it.y}%`, "--s": `${it.size}px`, "--d": it.depth,
            "--tilt": `${it.tilt || 0}deg`, "--rot": `${it.rot || 0}deg`, "--i": i,
          }}
        >
          {it.kind === "cell" && <span className="nucleus" />}
          {it.kind === "aster" && <span className="spokes" />}
        </div>
      ))}
    </div>
  );
}
