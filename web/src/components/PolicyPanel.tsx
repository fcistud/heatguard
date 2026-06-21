import { useEffect, useState } from "react";
import { api, ApiError } from "../api";
import type { PolicyAnswer } from "../types";

export function PolicyPanel() {
  const [presets, setPresets] = useState<string[]>([]);
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<PolicyAnswer | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .policyDemoQuestions()
      .then(setPresets)
      .catch(() => {
        /* optional — panel still works with manual input */
      });
  }, []);

  async function run(q: string) {
    const text = q.trim();
    if (!text) return;
    setQuestion(text);
    setLoading(true);
    setError(null);
    try {
      const res = await api.policyQuery(text);
      setResult(res);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Query failed");
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <div className="space-y-3">
        <p className="text-sm text-slate-600">
          TF-IDF retrieval over committed GCC ban summaries and ILO Water-Rest-Shade
          excerpts — cited, extractive answers (no external LLM).
        </p>
        {presets.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {presets.map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => run(p)}
                className="rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-left text-xs font-medium text-slate-700 shadow-sm transition hover:border-indigo-300 hover:bg-indigo-50"
              >
                {p}
              </button>
            ))}
          </div>
        )}
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          rows={3}
          placeholder="Ask about GCC midday bans, Qatar WBGT, or ILO WRS evidence…"
          className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-800 shadow-sm focus:border-indigo-400 focus:outline-none focus:ring-1 focus:ring-indigo-400"
        />
        <button
          type="button"
          onClick={() => run(question)}
          disabled={loading || !question.trim()}
          className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:opacity-60"
        >
          {loading ? "Searching corpus…" : "Query policy corpus"}
        </button>
        {error && <p className="text-sm text-red-600">{error}</p>}
      </div>

      <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
        {!result && !error && (
          <div className="flex min-h-[12rem] items-center justify-center text-center text-sm text-slate-400">
            Pick a preset or type a question about Gulf heat-work policy.
          </div>
        )}
        {result && (
          <div className="space-y-4">
            <div className="whitespace-pre-wrap text-sm leading-relaxed text-slate-700">
              {result.answer}
            </div>
            {result.sources.length > 0 && (
              <div>
                <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Sources
                </div>
                <ul className="mt-2 space-y-2">
                  {result.sources.map((s) => (
                    <li
                      key={`${s.doc_id}-${s.chunk_index}`}
                      className="rounded-lg border border-slate-200 bg-white p-3 text-xs text-slate-600"
                    >
                      <div className="font-semibold text-slate-800">
                        {s.title}{" "}
                        <span className="font-normal text-slate-400">
                          (score {s.score.toFixed(3)})
                        </span>
                      </div>
                      <p className="mt-1 leading-relaxed">{s.excerpt}</p>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
