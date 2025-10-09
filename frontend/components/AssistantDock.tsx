"use client";

import { useEffect, useRef, useState } from "react";
import clsx from "clsx";

export default function AssistantDock({ apiUrl }: { apiUrl: string }) {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<{ role: "user" | "assistant"; content: string }[]>([
    { role: "assistant", content: "Olá! Sou seu copiloto de estudos. Como posso ajudar?" },
  ]);
  const [loading, setLoading] = useState(false);
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, open]);

  const send = async () => {
    if (!input.trim() || loading) return;
    const text = input.trim();
    setInput("");
    setMessages((m) => [...m, { role: "user", content: text }]);
    setLoading(true);
    try {
      const r = await fetch(`${apiUrl}/coach`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ subject: "Assistente", activity: text }),
      });
      const d = await r.json();
      const reply = d?.summary || d?.message || JSON.stringify(d);
      setMessages((m) => [...m, { role: "assistant", content: String(reply) }]);
    } catch (e) {
      setMessages((m) => [...m, { role: "assistant", content: "Tive um problema para responder agora." }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <button
        aria-label="Abrir assistente"
        className="fixed bottom-5 right-5 z-[55] h-14 w-14 rounded-full bg-primary text-white shadow-xl border border-primary/60 hover:opacity-90"
        onClick={() => setOpen((o) => !o)}
      >
        {open ? "×" : "IA"}
      </button>

      <div className={clsx("fixed bottom-24 right-5 z-[55] w-[min(420px,95vw)] transform transition-all", open ? "translate-y-0 opacity-100" : "translate-y-6 opacity-0 pointer-events-none")}>
        <div className="rounded-2xl border border-panel bg-white shadow-2xl overflow-hidden">
          <header className="px-4 py-3 border-b border-panel text-secondary font-semibold">Assistente</header>
          <div className="p-3 max-h-[50vh] overflow-auto space-y-2 text-sm">
            {messages.map((m, i) => (
              <div key={i} className={clsx("px-3 py-2 rounded-lg w-fit max-w-[85%]", m.role === "assistant" ? "bg-surface border border-panel" : "bg-primary text-white ml-auto")}>{m.content}</div>
            ))}
            {loading && <div className="px-3 py-2 rounded-lg w-fit max-w-[85%] bg-surface border border-panel">Digitando…</div>}
            <div ref={endRef} />
          </div>
          <div className="p-3 border-t border-panel flex items-center gap-2">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') send(); }}
              placeholder="Pergunte algo…"
              className="flex-1 outline-none"
              aria-label="Campo do assistente"
            />
            <button onClick={send} className="px-3 py-2 rounded-lg bg-primary text-white disabled:opacity-50" disabled={loading || !input.trim()}>Enviar</button>
          </div>
        </div>
      </div>
    </>
  );
}
