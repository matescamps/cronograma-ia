"use client";

import { useEffect, useRef, useState } from "react";
import clsx from "clsx";

interface CommandBarProps {
  open: boolean;
  setOpen: (v: boolean) => void;
  onNavigate: (sectionId: string) => void;
  onToggleTheme?: () => void;
}

const COMMANDS = [
  { id: "progress-section", label: "Salvar Progresso" },
  { id: "meta-section", label: "Salvar Metas" },
  { id: "pomodoro-section", label: "Iniciar Pomodoro" },
  { id: "quiz-section", label: "Gerar Quiz Relâmpago" },
  { id: "history-section", label: "Ver Histórico" },
  { id: "toggle-theme", label: "Alternar tema" },
];

export default function CommandBar({ open, setOpen, onNavigate, onToggleTheme }: CommandBarProps) {
  const [query, setQuery] = useState("");
  const inputRef = useRef<HTMLInputElement | null>(null);
  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 0);
    }
  }, [open]);

  const filtered = COMMANDS.filter(c => c.label.toLowerCase().includes(query.toLowerCase()));

  return (
    <div className={clsx("fixed inset-0 z-50", open ? "block" : "hidden")} aria-hidden={!open} role="dialog" aria-modal="true">
      <div className="absolute inset-0 bg-black/30" onClick={() => setOpen(false)} />
      <div className="relative mx-auto max-w-xl mt-24">
        <div className="bg-white rounded-xl border border-panel shadow-xl overflow-hidden">
          <div className="p-3 border-b border-panel">
            <input
              ref={inputRef}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Digite um comando..."
              className="w-full outline-none"
              aria-label="Command Bar"
            />
          </div>
          <ul className="max-h-64 overflow-auto">
            {filtered.map((c) => (
              <li key={c.id}>
                <button
                  className="w-full text-left px-4 py-3 hover:bg-surface"
                  onClick={() => { setOpen(false); if (c.id === 'toggle-theme') { onToggleTheme?.(); } else { onNavigate(c.id); } }}
                >{c.label}</button>
              </li>
            ))}
            {filtered.length === 0 && <li className="px-4 py-3 text-muted">Sem resultados</li>}
          </ul>
        </div>
      </div>
    </div>
  );
}
