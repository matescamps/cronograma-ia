"use client";

import { useState } from "react";
import clsx from "clsx";

const INPUT_CLASS = "w-full border border-panel rounded-lg p-2 bg-white text-secondary focus:outline-none focus:ring-2 focus:ring-primary";
export interface ProgressEditorProps {
  user: string;
  apiUrl: string;
  defaultPlanned?: number | string;
  defaultDone?: number | string;
  defaultTheoryDone?: boolean;
  defaultPercent?: number | string;
  defaultStatus?: string;
  onSaved?: () => void;
  id?: string;
}

export default function ProgressEditor({
  user,
  apiUrl,
  defaultPlanned,
  defaultDone,
  defaultTheoryDone,
  defaultPercent,
  defaultStatus,
  onSaved,
  id,
}: ProgressEditorProps) {
  const [planned, setPlanned] = useState<string>(String(defaultPlanned ?? ""));
  const [done, setDone] = useState<string>(String(defaultDone ?? ""));
  const [theoryDone, setTheoryDone] = useState<boolean>(Boolean(defaultTheoryDone));
  const [percent, setPercent] = useState<string>(String(defaultPercent ?? ""));
  const [status, setStatus] = useState<string>(String(defaultStatus ?? ""));

  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: "ok" | "err"; text: string } | null>(null);

  const submit = async () => {
    setSaving(true);
    setMessage(null);
    try {
      const body: any = { user };
      if (planned !== "") body.questoes_planejadas = Number(planned);
      if (done !== "") body.questoes_feitas = Number(done);
      body.teoria_feita = Boolean(theoryDone);
      if (percent !== "") body.percentual_concluido = Number(percent);
      if (status.trim() !== "") body.status = status.trim();

      const res = await fetch(`${apiUrl}/update_progress`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail || "Falha ao salvar progresso");
      }
      setMessage({ type: "ok", text: "Progresso salvo." });
      onSaved?.();
    } catch (e: any) {
      setMessage({ type: "err", text: e?.message || "Erro inesperado" });
    } finally {
      setSaving(false);
    }
  };

  return (
    <section id={id} className="space-y-3">
      <h3 className="font-semibold text-secondary">Progresso</h3>
      <div className="grid grid-cols-2 md:grid-cols-6 gap-3 items-end">
        <LabeledInput label="Questões Planejadas" type="number" value={planned} onChange={setPlanned} min={0} />
        <LabeledInput label="Questões Feitas" type="number" value={done} onChange={setDone} min={0} />
        <Toggle label="Teoria Feita" checked={theoryDone} onChange={setTheoryDone} />
        <LabeledInput label="% Concluído" type="number" value={percent} onChange={setPercent} min={0} max={100} suffix="%" />
        <div className="col-span-2 md:col-span-2">
          <label className="block text-sm text-muted mb-1">Status</label>
          <select
            className={INPUT_CLASS}
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            <option value="">—</option>
            <option>Em andamento</option>
            <option>Concluído</option>
            <option>Adiado</option>
            <option>Bloqueado</option>
          </select>
        </div>
      </div>
      <div className="flex items-center gap-3">
        <button
          onClick={submit}
          disabled={saving}
          className={clsx(
            "px-4 py-2 rounded-lg bg-primary text-white hover:opacity-90",
            saving && "opacity-70 cursor-not-allowed"
          )}
        >
          {saving ? "Salvando..." : "Salvar"}
        </button>
        {message && (
          <span className={clsx("text-sm", message.type === "ok" ? "text-success" : "text-red-500")}>{message.text}</span>
        )}
      </div>
    </section>
  );
}

function LabeledInput({ label, type = "text", value, onChange, min, max, suffix }:
  { label: string; type?: string; value: string; onChange: (v: string) => void; min?: number; max?: number; suffix?: string }) {
  return (
    <div>
      <label className="block text-sm text-muted mb-1">{label}</label>
      <div className="flex items-center gap-2">
        <input
          aria-label={label}
          type={type}
          value={value}
          min={min}
          max={max}
          onChange={(e) => onChange(e.target.value)}
          className={INPUT_CLASS}
        />
        {suffix && <span className="text-muted text-sm">{suffix}</span>}
      </div>
    </div>
  );
}

function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <div>
      <label className="block text-sm text-muted mb-1">{label}</label>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={clsx(
          "w-full flex items-center justify-between border border-panel rounded-lg px-3 py-2 bg-white",
          checked ? "text-secondary" : "text-muted"
        )}
      >
        <span>{checked ? "Sim" : "Não"}</span>
        <span
          aria-hidden
          className={clsx(
            "relative inline-flex h-6 w-11 items-center rounded-full transition-colors",
            checked ? "bg-primary" : "bg-panel"
          )}
        >
          <span
            className={clsx(
              "inline-block h-4 w-4 transform rounded-full bg-white transition-transform",
              checked ? "translate-x-6" : "translate-x-1"
            )}
          />
        </span>
      </button>
    </div>
  );
}
