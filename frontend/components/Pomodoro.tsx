"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import clsx from "clsx";

export interface PomodoroProps {
  onFocusComplete?: (points: number) => void;
  id?: string;
}

const MODES = [
  { key: "25/5", label: "25/5", focusMin: 25, breakMin: 5, points: 25 },
  { key: "50/10", label: "50/10", focusMin: 50, breakMin: 10, points: 50 },
  { key: "quick", label: "Simulado rápido", focusMin: 20, breakMin: 0, points: 20 },
] as const;

type ModeKey = typeof MODES[number]["key"];

export default function Pomodoro({ onFocusComplete, id }: PomodoroProps) {
  const [mode, setMode] = useState<ModeKey>("25/5");
  const cfg = useMemo(() => MODES.find((m) => m.key === mode)!, [mode]);

  const [secondsLeft, setSecondsLeft] = useState(cfg.focusMin * 60);
  const [running, setRunning] = useState(false);
  const [onBreak, setOnBreak] = useState(false);

  const intervalRef = useRef<number | null>(null);

  useEffect(() => {
    // Reset when mode changes
    setRunning(false);
    setOnBreak(false);
    setSecondsLeft(cfg.focusMin * 60);
  }, [cfg.focusMin]);

  useEffect(() => {
    if (!running) return;
    intervalRef.current = window.setInterval(() => {
      setSecondsLeft((s) => s - 1);
    }, 1000);
    return () => {
      if (intervalRef.current) window.clearInterval(intervalRef.current);
    };
  }, [running]);

  useEffect(() => {
    if (secondsLeft >= 0) return;
    // Phase ended
    if (!onBreak) {
      // Focus completed
      const points = cfg.points;
      const currentXp = Number(localStorage.getItem("focus_xp") || "0");
      const nextXp = currentXp + points;
      localStorage.setItem("focus_xp", String(nextXp));
      onFocusComplete?.(points);
      notify("Foco concluído", `+${points} XP`);
      if (cfg.breakMin > 0) {
        setOnBreak(true);
        setSecondsLeft(cfg.breakMin * 60);
      } else {
        setRunning(false);
        setOnBreak(false);
        setSecondsLeft(cfg.focusMin * 60);
      }
    } else {
      // Break finished; reset
      setOnBreak(false);
      setRunning(false);
      setSecondsLeft(cfg.focusMin * 60);
      notify("Intervalo concluído", "Vamos voltar ao foco");
    }
  }, [secondsLeft, onBreak, cfg.points, cfg.breakMin, cfg.focusMin, onFocusComplete]);

  const start = () => setRunning(true);
  const pause = () => setRunning(false);
  const reset = () => { setRunning(false); setOnBreak(false); setSecondsLeft(cfg.focusMin * 60); };

  const mm = Math.max(0, Math.floor(secondsLeft / 60));
  const ss = Math.max(0, secondsLeft % 60);
  const display = `${String(mm).padStart(2, "0")}:${String(ss).padStart(2, "0")}`;

  const total = (onBreak ? cfg.breakMin : cfg.focusMin) * 60;
  const progress = 100 - Math.round((secondsLeft / Math.max(1, total)) * 100);

  return (
    <section id={id} className="space-y-3">
      <h3 className="font-semibold text-secondary">Pomodoro</h3>
      <div className="flex flex-wrap gap-2">
        {MODES.map((m) => (
          <button
            key={m.key}
            onClick={() => setMode(m.key)}
            className={clsx(
              "px-3 py-1 rounded-full border",
              mode === m.key ? "bg-primary text-white border-primary" : "bg-surface text-secondary border-panel"
            )}
          >{m.label}</button>
        ))}
      </div>
      <div className="bg-white border border-panel rounded-2xl p-6 text-center">
        <div className="text-5xl font-bold text-secondary tabular-nums mb-3">{display}</div>
        <div className="h-2 w-full bg-panel rounded-full overflow-hidden mb-4">
          <div className={clsx("h-full transition-all", onBreak ? "bg-success" : "bg-primary")} style={{ width: `${progress}%` }} />
        </div>
        <div className="flex items-center justify-center gap-3">
          {!running ? (
            <button onClick={start} className="px-4 py-2 rounded-lg bg-primary text-white hover:opacity-90">Iniciar</button>
          ) : (
            <button onClick={pause} className="px-4 py-2 rounded-lg border border-panel text-secondary hover:border-primary hover:text-primary">Pausar</button>
          )}
          <button onClick={reset} className="px-4 py-2 rounded-lg border border-panel text-secondary hover:border-primary hover:text-primary">Resetar</button>
          <span className="text-muted text-sm">{onBreak ? "Intervalo" : "Foco"}</span>
        </div>
      </div>
    </section>
  );
}

function notify(title: string, desc?: string) {
  try {
    if (navigator?.vibrate) navigator.vibrate(80);
    // simple beep using WebAudio
    const ctx = (window as any).audioContext || new (window.AudioContext || (window as any).webkitAudioContext)();
    ;(window as any).audioContext = ctx;
    const o = ctx.createOscillator();
    const g = ctx.createGain();
    o.type = 'sine';
    o.frequency.value = 880;
    o.connect(g); g.connect(ctx.destination);
    g.gain.setValueAtTime(0.001, ctx.currentTime);
    g.gain.exponentialRampToValueAtTime(0.2, ctx.currentTime + 0.01);
    g.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.18);
    o.start(); o.stop(ctx.currentTime + 0.2);
    // toast
    const evt = new CustomEvent('focusos:toast', { detail: { id: `${Date.now()}-${Math.random()}`, title, description: desc, type: 'success' } });
    // @ts-ignore
    window.dispatchEvent(evt);
  } catch {}
}
