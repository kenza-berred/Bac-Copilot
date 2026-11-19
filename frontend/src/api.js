async function call(path, options = {}) {
  const res = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} — ${text.slice(0, 300)}`);
  }
  return res.json();
}

export const api = {
  health: () => call("/health"),
  concepts: () => call("/concepts"),
  chat: (student_id, message, history) => call("/chat", { method: "POST", body: { student_id, message, history } }),
  quiz: (student_id, n, concepts, kinds) => call("/quiz", { method: "POST", body: { student_id, n, concepts, kinds } }),
  grade: (body) => call("/grade", { method: "POST", body }),
  student: (id) => call(`/students/${encodeURIComponent(id)}`),
  documents: () => call("/documents"),
  ingest: () => call("/ingest", { method: "POST" }),
  upload: async (file, title) => {
    const form = new FormData();
    form.append("file", file);
    if (title) form.append("title", title);
    const res = await fetch("/api/documents/upload", { method: "POST", body: form });
    if (!res.ok) throw new Error(`${res.status} — ${(await res.text()).slice(0, 300)}`);
    return res.json();
  },
  studyPack: (docId) => call(`/documents/${encodeURIComponent(docId)}/study`),
  regenerateStudyPack: (docId) => call(`/documents/${encodeURIComponent(docId)}/study`, { method: "POST", body: {} }),
};

export const pdfUrl = (docId, page) => `/api/documents/${encodeURIComponent(docId)}/pdf#page=${page || 1}`;
