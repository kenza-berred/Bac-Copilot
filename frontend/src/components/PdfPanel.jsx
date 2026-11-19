import { pdfUrl } from "../api.js";

export default function PdfPanel({ pdf, onClose }) {
  return (
    <aside className="pdf-panel">
      <header>
        <div>
          <strong>{pdf.title || pdf.doc_id}</strong>
          <small>page {pdf.page}</small>
        </div>
        <div>
          <a href={pdfUrl(pdf.doc_id, pdf.page)} target="_blank" rel="noreferrer">Ouvrir</a>
          <button onClick={onClose} aria-label="Fermer">✕</button>
        </div>
      </header>
      {/* key forces a reload when only the #page fragment changes */}
      <iframe key={`${pdf.doc_id}-${pdf.page}`} src={pdfUrl(pdf.doc_id, pdf.page)} title="Document source" />
    </aside>
  );
}
