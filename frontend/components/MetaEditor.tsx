"use client";

import { useState } from "react";
import clsx from "clsx";

export interface MetaEditorProps {
  user: string;
  apiUrl: string;
  defaultDificuldade?: number | string;
  defaultPrioridade?: string;
  defaultSituacao?: string;
  defaultAlerta?: string;
  defaultFase?: string;
  onSaved?: () => void;
  id?: string;
}

export default function MetaEditor({
  user,
  apiUrl,
  defaultDificuldade,
  defaultPrioridade,
  defaultSituacao,
  defaultAlerta,
  defaultFase,
  onSaved,
  id,
}: MetaEditorProps) {
  const inputClass = "w-full border border-panel rounded-lg p-2 bg-white text-secondary focus:outline-none focus:ring-2 focus:ring-primary";
  const [dificuldade, setDificuldade] = useState<string>(String(defaultDificuldade ?? ""));
  const [prioridade, setPrioridade] = useState<string>(String(defaultPrioridade ?? ""));
  const [situacao, setSituacao] = useState<string>(String(defaultSituacao ?? ""));
  const [alerta, setAlerta] = useState<string>(String(defaultAlerta ?? ""));
  const [fase, setFase] = useState<string>(String(defaultFase ?? ""));
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: "ok" | "err"; text: string } | null>(null);

  const submit = async () => {
    setSaving(true);
    setMessage(null);
    try {
      const body: any = { user };
      if (dificuldade !== "") body.dificuldade = Number(dificuldade);
      if (prioridade.trim() !== "") body.prioridade = prioridade.trim();
      if (situacao.trim() !== "") body.situacao = situacao.trim();
      if (alerta.trim() !== "") body.alerta = alerta.trim();
      if (fase.trim() !== "") body.fase_plano = fase.trim();

      const res = await fetch(`${apiUrl}/update_meta`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail || "Falha ao salvar metas");
      }
      setMessage({ type: "ok", text: "Metas salvas." });
      onSaved?.();
    } catch (e: any) {
      setMessage({ type: "err", text: e?.message || "Erro inesperado" });
    } finally {
      setSaving(false);
    }
  };

  return (
    <section id={id} className="space-y-3">
      <h3 className="font-semibold text-secondary">Metas do Dia</h3>
      <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
        <LabeledInput label="Dificuldade (1-5)" type="number" value={dificuldade} onChange={setDificuldade} min={1} max={5} />
        <LabeledInput label="Prioridade" value={prioridade} onChange={setPrioridade} />
        <LabeledInput label="Situação" value={situacao} onChange={setSituacao} />
        <LabeledInput label="Alerta/Comentário" value={alerta} onChange={setAlerta} />
        <LabeledInput label="Fase do Plano" value={fase} onChange={setFase} />
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
          {saving ? "Salvando..." : "Salvar metas"}
        </button>
        {message && (
          <span className={clsx("text-sm", message.type === "ok" ? "text-success" : "text-red-500")}>{message.text}</span>
        )}
      </div>
    </section>
  );
}

function LabeledInput({ label, type = "text", value, onChange, min, max }:
  { label: string; type?: string; value: string; onChange: (v: string) => void; min?: number; max?: number }) {
  return (
    <div>
      <label className="block text-sm text-muted mb-1">{label}</label>
      <input
        aria-label={label}
        type={type}
        value={value}
        min={min}
        max={max}
        onChange={(e) => onChange(e.target.value)}
        className={inputClass}
      />
    </div>
  );
}
