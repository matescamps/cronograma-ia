"use client";

import { useEffect, useState } from "react";

interface HistoryPoint { date: string; percent: number | null; difficulty: number | null }

export default function HistoryChart({ user, apiUrl, id }: { user: string; apiUrl: string; id?: string }) {
  const [points, setPoints] = useState<HistoryPoint[]>([]);

  useEffect(() => {
    const load = async () => {
      try {
        const res = await fetch(`${apiUrl}/history/${user}`);
        const data = await res.json();
        setPoints(data.history || []);
      } catch {
        setPoints([]);
      }
    };
    load();
  }, [apiUrl, user]);

  return (
    <section id={id} className="space-y-3">
      <h3 className="font-semibold text-secondary">Histórico (14 dias)</h3>
      <div className="bg-white border border-panel rounded-2xl p-4">
        {points.length === 0 && <div className="text-muted">Sem histórico recente.</div>}
        {points.length > 0 && (
          <div className="grid grid-cols-14 gap-2 items-end" style={{ gridTemplateColumns: `repeat(${points.length}, minmax(0, 1fr))` }}>
            {points.map((p, i) => (
              <div key={i} className="flex flex-col items-center gap-2">
                <div className="relative h-24 w-full">
                  {/* percent dot */}
                  {typeof p.percent === 'number' && (
                    <div
                      className="absolute left-1/2 -translate-x-1/2 h-2 w-2 rounded-full bg-primary"
                      style={{ top: `${100 - Math.max(0, Math.min(100, p.percent))}%` }}
                      title={`% ${p.percent}`}
                    />
                  )}
                  {/* difficulty bar */}
                  {typeof p.difficulty === 'number' && (
                    <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-3 bg-secondary/20 rounded"
                      style={{ height: `${(Math.max(1, Math.min(5, p.difficulty)) / 5) * 100}%` }}
                      title={`Dif ${p.difficulty}`}
                    />
                  )}
                </div>
                <div className="text-[10px] text-muted">{p.date}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
