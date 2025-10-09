"use client";

import { useEffect, useMemo, useState } from "react";
import clsx from "clsx";

interface Question {
  type: "mcq" | "truefalse";
  question: string;
  options?: string[];
  answer: string;
  explanation?: string;
}

export interface QuizProps {
  user: string;
  subject?: string;
  apiUrl: string;
  id?: string;
}

export default function Quiz({ user, subject, apiUrl, id }: QuizProps) {
  const [topic, setTopic] = useState(subject || "Revisão médica");
  const [mode, setMode] = useState<"mixed" | "mcq" | "truefalse">("mixed");
  const [count, setCount] = useState(3);
  const [loading, setLoading] = useState(false);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [showResult, setShowResult] = useState(false);

  const normalizeQuestions = (raw: any): Question[] => {
    const arr = Array.isArray(raw?.questions) ? raw.questions : [];
    return arr.map((q: any) => {
      const type = q?.type === 'truefalse' ? 'truefalse' : 'mcq';
      const answer = String(q?.answer ?? '').toLowerCase();
      let normalizedAnswer = q?.answer;
      if (type === 'truefalse') {
        normalizedAnswer = answer === 'true' || answer === 'verdadeiro' ? 'true' : 'false';
      }
      return {
        type,
        question: String(q?.question ?? ''),
        options: Array.isArray(q?.options) ? q.options : undefined,
        answer: normalizedAnswer,
        explanation: q?.explanation ? String(q.explanation) : undefined,
      } as Question;
    }).filter((q: Question) => q.question);
  };

  const generate = async () => {
    setLoading(true);
    setShowResult(false);
    setQuestions([]);
    setAnswers({});
    try {
      const res = await fetch(`${apiUrl}/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ topic, count, mode }),
      });
      const data = await res.json();
      setQuestions(normalizeQuestions(data));
    } catch (e) {
      setQuestions([]);
    } finally {
      setLoading(false);
    }
  };

  const score = useMemo(() => {
    return questions.reduce((acc, q, idx) => acc + (answers[idx] === String(q.answer) ? 1 : 0), 0);
  }, [answers, questions]);

  useEffect(() => {
    // auto-generate on first mount
    generate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <section id={id} className="space-y-3">
      <h3 className="font-semibold text-secondary">Quiz Relâmpago</h3>
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3 items-end">
        <LabeledInput label="Tópico" value={topic} onChange={setTopic} />
        <div>
          <label className="block text-sm text-muted mb-1">Modo</label>
          <select
            className="w-full border border-panel rounded-lg p-2 bg-white text-secondary focus:outline-none focus:ring-2 focus:ring-primary"
            value={mode}
            onChange={(e) => setMode(e.target.value as any)}
          >
            <option value="mixed">Misto</option>
            <option value="mcq">MCQ</option>
            <option value="truefalse">V/F</option>
          </select>
        </div>
        <LabeledInput label="Quantidade" type="number" value={String(count)} onChange={(v) => setCount(Number(v))} min={3} max={5} />
        <button onClick={generate} className="px-4 py-2 rounded-lg bg-primary text-white hover:opacity-90">Gerar</button>
      </div>

      {loading && <div className="p-4 bg-panel rounded text-muted animate-pulse">Gerando questões...</div>}

      {!loading && questions.length > 0 && (
        <div className="space-y-4">
          {questions.map((q, idx) => (
            <div key={idx} className="border border-panel rounded-xl p-4 bg-white">
              <div className="font-medium text-secondary mb-2">{idx + 1}. {q.question}</div>
              {q.type === "mcq" ? (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                  {(q.options || []).map((opt, i) => (
                    <button
                      key={i}
                      onClick={() => setAnswers({ ...answers, [idx]: opt })}
                      className={clsx(
                        "text-left p-2 rounded border",
                        answers[idx] === opt ? "border-primary text-primary" : "border-panel text-secondary hover:border-primary/60"
                      )}
                    >{opt}</button>
                  ))}
                </div>
              ) : (
                <div className="flex gap-2">
                  {["true", "false"].map((opt) => (
                    <button
                      key={opt}
                      onClick={() => setAnswers({ ...answers, [idx]: opt })}
                      className={clsx(
                        "px-3 py-2 rounded border",
                        answers[idx] === opt ? "border-primary text-primary" : "border-panel text-secondary hover:border-primary/60"
                      )}
                    >{opt === "true" ? "Verdadeiro" : "Falso"}</button>
                  ))}
                </div>
              )}
              {showResult && (
                <div className={clsx("mt-3 text-sm", answers[idx] === String(q.answer) ? "text-success" : "text-red-500")}> 
                  {answers[idx] === String(q.answer) ? "Correto" : `Incorreto. Resp.: ${String(q.answer)}`}
                  {q.explanation && <div className="text-muted mt-1">{q.explanation}</div>}
                </div>
              )}
            </div>
          ))}
          <div className="flex items-center gap-3">
            <button onClick={() => setShowResult(true)} className="px-4 py-2 rounded-lg bg-primary text-white hover:opacity-90">Checar</button>
            {showResult && <span className="text-muted">Pontuação: {score}/{questions.length}</span>}
          </div>
        </div>
      )}
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
        className="w-full border border-panel rounded-lg p-2 bg-white text-secondary focus:outline-none focus:ring-2 focus:ring-primary"
      />
    </div>
  );
}
