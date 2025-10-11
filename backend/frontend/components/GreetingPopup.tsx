"use client";

import { useEffect, useMemo, useState } from "react";
import clsx from "clsx";

type Period = "Manhã" | "Tarde" | "Noite";

interface TaskRow {
  [key: string]: string;
}

export default function GreetingPopup({
  user,
  tasks,
  currentPeriod,
  apiUrl,
}: {
  user: string;
  tasks: TaskRow[];
  currentPeriod: Period;
  apiUrl: string;
}) {
  const [open, setOpen] = useState(false);
  const [sending, setSending] = useState<"none" | "questoes" | "teoria">("none");
  const [step, setStep] = useState<1 | 2>(1);

  const todayKey = useMemo(() => {
    const d = new Date();
    return `focus_greeting_shown_${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, "0")}${String(d.getDate()).padStart(2, "0")}`;
  }, []);

  const greetingText = useMemo(() => {
    const hour = new Date().getHours();
    if (hour < 12) return "Bom dia";
    if (hour < 18) return "Boa tarde";
    return "Boa noite";
  }, []);

  const subjectsForDay = useMemo(() => {
    if (!tasks || tasks.length === 0) return [] as { period: Period; subject?: string; activity?: string }[];
    const t = tasks[0] as Record<string, string>;
    const periods: Period[] = ["Manhã", "Tarde", "Noite"];
    return periods.map((p) => ({
      period: p,
      subject: t[`Matéria (${p})`],
      activity: t[`Atividade Detalhada (${p})`],
    }));
  }, [tasks]);

  useEffect(() => {
    // Show once per day after user loads their dashboard
    if (localStorage.getItem(todayKey)) return;
    setOpen(true);
  }, [todayKey]);

  const close = () => {
    localStorage.setItem(todayKey, "1");
    setOpen(false);
  };

  const onQuickLog = async (kind: "questoes" | "teoria") => {
    if (!user) return;
    setSending(kind);
    try {
      const body: any = { user };
      if (kind === "teoria") {
        body.teoria_feita = true;
        body.status = "Teoria";
      } else {
        body.teoria_feita = false;
        body.status = "Questões";
      }
      await fetch(`${apiUrl}/update_progress`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      setStep(2);
    } catch (e) {
      // ignore, this is a convenience log
    } finally {
      setSending("none");
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[60]" role="dialog" aria-modal="true" aria-label="Saudação do dia">
      <div className="absolute inset-0 bg-black/40" onClick={close} />
      <div className="relative mx-auto w-full max-w-xl mt-24 animate-fade-in">
        <div className="rounded-2xl border border-panel bg-white shadow-2xl overflow-hidden">
          <header className="px-5 py-4 bg-gradient-to-r from-primary/10 to-primary/0 border-b border-panel">
            <h2 className="text-xl font-bold text-secondary">{greetingText}, {user}!</h2>
            <p className="text-muted text-sm">Estas são as recomendações de estudo do seu cronograma de hoje.</p>
          </header>

          <div className="p-5 space-y-4">
            {step === 1 && (
              <>
                <div className="grid grid-cols-1 gap-3">
                  {subjectsForDay.map(({ period, subject, activity }) => (
                    <div key={period} className={clsx("rounded-xl border p-3", currentPeriod === period ? "border-primary/60 bg-primary/5" : "border-panel bg-surface")}>
                      <div className="flex items-center justify-between">
                        <div className="font-semibold text-secondary">{period}</div>
                        {currentPeriod === period && <span className="text-xs px-2 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20">agora</span>}
                      </div>
                      <div className="text-sm text-muted mt-1">
                        {subject ? <>
                          <span className="font-medium text-secondary">{subject}</span>
                          {activity && <span> • {activity}</span>}
                        </> : <span>Sem matéria definida</span>}
                      </div>
                    </div>
                  ))}
                </div>

                {currentPeriod === "Tarde" && (
                  <div className="mt-2">
                    <div className="text-sm text-secondary font-medium mb-2">Como foi seu período? Você focou em questões ou teoria?</div>
                    <div className="flex gap-3">
                      <button
                        onClick={() => onQuickLog("questoes")}
                        className={clsx("px-4 py-2 rounded-lg border", sending === "questoes" ? "bg-primary text-white border-primary" : "border-panel text-secondary hover:border-primary hover:text-primary")}
                        disabled={sending !== "none"}
                      >{sending === "questoes" ? "Enviando..." : "Marcar Questões"}</button>
                      <button
                        onClick={() => onQuickLog("teoria")}
                        className={clsx("px-4 py-2 rounded-lg border", sending === "teoria" ? "bg-primary text-white border-primary" : "border-panel text-secondary hover:border-primary hover:text-primary")}
                        disabled={sending !== "none"}
                      >{sending === "teoria" ? "Enviando..." : "Marcar Teoria"}</button>
                    </div>
                  </div>
                )}
              </>
            )}

            {step === 2 && (
              <div className="text-sm text-success">Anotado. Bom trabalho mantendo o ritmo!</div>
            )}
          </div>

          <footer className="px-5 py-4 border-t border-panel flex items-center justify-end gap-3">
            <button className="px-4 py-2 rounded-lg border border-panel text-secondary hover:border-primary hover:text-primary" onClick={close}>Fechar</button>
            <button className="px-4 py-2 rounded-lg bg-primary text-white hover:opacity-90" onClick={close}>Começar</button>
          </footer>
        </div>
      </div>
    </div>
  );
}
