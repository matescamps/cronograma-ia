'use client';

import { useState, useEffect, useMemo } from 'react';
import clsx from 'clsx';

interface Task {
  'Data': string;
  'Aluno(a)': string;
  'Matéria (Manhã)': string; 'Atividade Detalhada (Manhã)': string;
  'Matéria (Tarde)': string; 'Atividade Detalhada (Tarde)': string;
  'Matéria (Noite)': string; 'Atividade Detalhada (Noite)': string;
}
interface CoachAdvice {
  summary: string;
  flashcards: { q: string; a: string; }[];
}

export default function FocusOS() {
  const [user, setUser] = useState<string | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [streakDays, setStreakDays] = useState<number>(0);

  const currentPeriod = useMemo(() => {
    const hour = new Date().getHours();
    if (hour < 12) return 'Manhã';
    if (hour < 18) return 'Tarde';
    return 'Noite';
  }, []);

  useEffect(() => {
    const stored = Number(localStorage.getItem('focus_streak') || '0');
    setStreakDays(stored);
  }, []);

  useEffect(() => {
    if (user) {
      const fetchTasks = async () => {
        setLoading(true);
        setError(null);
        try {
          const apiUrl = resolveApiUrl();
          if (!apiUrl) {
            throw new Error('Configuração ausente: defina NEXT_PUBLIC_API_URL no Vercel apontando para o backend (HTTPS).');
          }
          if (typeof window !== 'undefined' && window.location.protocol === 'https:' && apiUrl.startsWith('http://')) {
            throw new Error('Requisição bloqueada: frontend em HTTPS não pode chamar backend HTTP. Use URL HTTPS no NEXT_PUBLIC_API_URL.');
          }
          const ctrl = new AbortController();
          const timeoutId = setTimeout(() => ctrl.abort(), 15000);
          const response = await fetch(`${apiUrl}/tasks/${user}`, { signal: ctrl.signal });
          clearTimeout(timeoutId);
          if (!response.ok) {
            const errData = await response.json();
            throw new Error(errData.detail || 'Falha ao buscar missões.');
          }
          setTasks(await response.json());
        } catch (err) {
          const msg = err instanceof Error ? err.message : 'Um erro inesperado ocorreu.';
          setError(msg);
        } finally {
          setLoading(false);
        }
      };
      fetchTasks();
    }
  }, [user]);

  if (!user) return <LoginScreen onLogin={setUser} />;

  return (
    <main className="relative max-w-6xl mx-auto p-4 md:p-8 animate-fade-in">
      <Header user={user} streakDays={streakDays} onLogout={() => setUser(null)} />
      {loading && <StatusDisplay message="Sincronizando com o satélite de missões..." />}
      {error && <StatusDisplay message={`ERRO DE CONEXÃO: ${error}`} isError />}
      {!loading && !error && (
        <MissionControl tasks={tasks} period={currentPeriod} onComplete={() => incrementStreak(setStreakDays)} />
      )}
      <AssistantWidget />
    </main>
  );
}

const LoginScreen = ({ onLogin }: { onLogin: (user: string) => void }) => (
  <div className="flex items-center justify-center min-h-screen">
    <div className="bg-surface p-8 rounded-lg shadow-2xl text-center w-full max-w-xl animate-fade-in">
      <h1 className="text-4xl font-extrabold text-secondary mb-2">Cronograma A&M</h1>
      <p className="text-muted mb-8">Seleção de Operador</p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <button onClick={() => onLogin('Ana')} className="w-full bg-white text-secondary border border-panel font-bold py-4 px-6 rounded-xl shadow-sm hover:shadow-md transition-all hover:-translate-y-0.5 focus:outline-none focus:ring-2 focus:ring-primary">Entrar como Ana</button>
        <button onClick={() => onLogin('Mateus')} className="w-full bg-white text-secondary border border-panel font-bold py-4 px-6 rounded-xl shadow-sm hover:shadow-md transition-all hover:-translate-y-0.5 focus:outline-none focus:ring-2 focus:ring-primary">Entrar como Mateus</button>
      </div>
    </div>
  </div>
);

const Header = ({ user, streakDays, onLogout }: { user: string; streakDays: number; onLogout: () => void }) => (
  <header className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 mb-8">
    <div>
      <h1 className="text-2xl font-extrabold text-secondary">Boa tarde, {user}.</h1>
      <div className="flex items-center gap-3 text-sm mt-1">
        <StatusPill label="Planilha" colorClass="bg-success" stateKey="sheet" />
        <StatusPill label="IA" colorClass="bg-success" stateKey="ia" />
        <div className="flex items-center gap-1 text-muted">
          <span className="">🔥 Sequência de Foco:</span>
          <span className="font-semibold text-secondary">{streakDays} dias</span>
        </div>
      </div>
    </div>
    <button onClick={onLogout} className="text-muted hover:text-primary transition-colors">Sair</button>
  </header>
);

const StatusDisplay = ({ message, isError = false }: { message: string; isError?: boolean }) => (
  <div className={clsx("text-center p-8 bg-surface rounded-lg", isError ? "text-red-500" : "text-muted")}>
    {message}
  </div>
);

const MissionControl = ({ tasks, period, onComplete }: { tasks: Task[]; period: string; onComplete: () => void }) => {
  const currentTask = useMemo(() => {
    if (!tasks || tasks.length === 0) return null;
    const taskForPeriod = tasks[0];
    const subject = taskForPeriod[`Matéria (${period})` as keyof Task];
    if (subject) return { task: taskForPeriod, activePeriod: period };
    
    for (const p of ['Manhã', 'Tarde', 'Noite']) {
      const fallbackSubject = taskForPeriod[`Matéria (${p})` as keyof Task];
      if (fallbackSubject) return { task: taskForPeriod, activePeriod: p };
    }
    return null;
  }, [tasks, period]);

  if (!currentTask) {
    return <StatusDisplay message="Nenhuma missão para hoje. Aproveite o tempo de inatividade, operador." />;
  }
  
  const { task, activePeriod } = currentTask;
  const subject = task[`Matéria (${activePeriod})` as keyof Task] as string;
  const activity = task[`Atividade Detalhada (${activePeriod})` as keyof Task] as string;
  const planned = Number(task[`Questões Planejadas (${activePeriod})` as keyof Task] || 0);
  const done = Number(task[`Questões Feitas (${activePeriod})` as keyof Task] || 0);
  const pctStr = String(task[`% Concluído (${activePeriod})` as keyof Task] || '').replace('%','');
  const percent = isFinite(Number(pctStr)) ? Number(pctStr) : (planned > 0 ? Math.min(100, Math.round((done / planned) * 100)) : 0);

  return <MissionCard subject={subject} activity={activity} initialProgress={percent} onComplete={onComplete} />;
};

const MissionCard = ({ subject, activity, initialProgress = 0, onComplete }: { subject: string; activity: string; initialProgress?: number; onComplete: () => void }) => {
  const [advice, setAdvice] = useState<CoachAdvice | null>(null);
  const [loading, setLoading] = useState(true);
  const [progress, setProgress] = useState<number>(initialProgress);

  useEffect(() => {
    const fetchAdvice = async () => {
      setLoading(true);
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';
      const response = await fetch(`${apiUrl}/coach`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ subject, activity }),
      });
      const data = await response.json();
      setAdvice(data);
      setLoading(false);
    };
    fetchAdvice();
  }, [subject, activity]);

  const completeTask = () => {
    onComplete();
  };

  return (
    <div className="bg-white border border-panel rounded-2xl p-6 shadow-sm">
      <h2 className="text-3xl font-extrabold text-secondary mb-1">{subject}</h2>
      <p className="text-primary text-lg mb-4">{activity}</p>

      <div className="h-2 w-full bg-panel rounded-full overflow-hidden mb-6">
        <div className="h-full bg-primary transition-all" style={{ width: `${progress}%` }} />
      </div>
      <div className="text-xs text-muted mb-4">Progresso: {progress}%</div>

      {loading && <div className="text-center p-4 bg-panel rounded-md text-muted animate-pulse">Recebendo transmissão do System Coach...</div>}
      {advice && (
        <div className="space-y-6">
          <div className="border-l-4 border-primary pl-4">
            <h3 className="font-semibold text-secondary mb-2">PLANO DE AÇÃO TÁTICO</h3>
            <PlanList summary={advice.summary} />
          </div>
          <div>
            <h3 className="font-semibold text-secondary mb-3">FLASHCARDS</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {advice.flashcards.map((card, i) => <Flashcard key={i} front={card.q} back={card.a} />)}
            </div>
          </div>
          <div className="flex items-center justify-between pt-2">
            <button className="px-4 py-2 rounded-lg border border-panel text-secondary hover:border-primary hover:text-primary transition-colors" onClick={() => setProgress(p => Math.min(100, p + 25))}>+ Progresso</button>
            <button className="px-4 py-2 rounded-lg bg-primary text-white hover:opacity-90" onClick={completeTask}>Marcar como concluída</button>
          </div>
        </div>
      )}
    </div>
  );
};

const Flashcard = ({ front, back }: { front: string; back: string }) => {
  const [isFlipped, setIsFlipped] = useState(false);
  return (
    <div className="perspective h-40" onClick={() => setIsFlipped(!isFlipped)}>
      <div className={clsx(
        "relative w-full h-full transform-style-3d transition-transform duration-700",
        isFlipped && "rotate-y-180"
      )}>
        <div className="absolute w-full h-full backface-hidden flex items-center justify-center p-4 rounded-xl bg-surface border border-panel text-center cursor-pointer shadow-sm hover:shadow-md">
          <p className="text-secondary select-none">{front}</p>
        </div>
        <div className="absolute w-full h-full backface-hidden flex items-center justify-center p-4 rounded-xl bg-primary text-white text-center cursor-pointer rotate-y-180 shadow-[0_0_30px_rgba(37,99,235,0.4)]">
          <p className="font-semibold select-none">{back}</p>
        </div>
      </div>
    </div>
  );
};

function incrementStreak(setter: (updater: (prev: number) => number) => void) {
  const today = new Date().toDateString();
  const key = 'focus_streak';
  const metaKey = 'focus_streak_last_completion';
  const stored = Number(localStorage.getItem(key) || '0');
  const last = localStorage.getItem(metaKey);
  if (last !== today) {
    const next = stored + 1;
    localStorage.setItem(key, String(next));
    localStorage.setItem(metaKey, today);
    setter(() => next);
  } else {
    setter(() => stored);
  }
}

function StatusPill({ label, colorClass, stateKey }: { label: string; colorClass: string; stateKey: 'sheet' | 'ia' }) {
  const [online, setOnline] = useState<boolean>(false);
  useEffect(() => {
    const apiUrl = resolveApiUrl();
    if (!apiUrl) { setOnline(false); return; }
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), 8000);
    fetch(`${apiUrl}/status`, { signal: ctrl.signal })
      .then(r => r.json())
      .then((s) => {
        setOnline(Boolean(s?.[stateKey]?.online));
      })
      .catch(() => setOnline(false))
      .finally(() => clearTimeout(t));
  }, [stateKey]);
  return (
    <span className={clsx('inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs', 'bg-surface border border-panel text-muted')}>
      <span className={clsx('h-2 w-2 rounded-full', online ? colorClass : 'bg-red-500')} />
      <span>{label}: {online ? 'Online' : 'Offline'}</span>
    </span>
  );
}

function resolveApiUrl(): string {
  const envUrl = process.env.NEXT_PUBLIC_API_URL || '';
  return envUrl;
}

function PlanList({ summary }: { summary: string }) {
  if (!summary) return null;
  const items = summary
    .split(/\n|\.|;|\u2022|\d+\)/)
    .map(s => s.trim())
    .filter(Boolean);
  if (items.length <= 1) {
    return <p className="text-muted">{summary}</p>;
  }
  return (
    <ol className="list-decimal ml-6 text-muted space-y-1">
      {items.map((step, idx) => (
        <li key={idx}>{step}</li>
      ))}
    </ol>
  );
}

function AssistantWidget() {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<{ role: 'user'|'ai'; content: string }[]>([]);
  const [sending, setSending] = useState(false);

  const send = async () => {
    if (!input.trim() || sending) return;
    const question = input.trim();
    setMessages(m => [...m, { role: 'user', content: question }]);
    setInput('');
    setSending(true);
    try {
      const apiUrl = resolveApiUrl();
      const resp = await fetch(`${apiUrl}/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: question })
      });
      const data = await resp.json();
      setMessages(m => [...m, { role: 'ai', content: data.answer || '...' }]);
    } catch {
      setMessages(m => [...m, { role: 'ai', content: 'Falha ao contatar a IA.' }]);
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="fixed bottom-6 right-6">
      {!open ? (
        <button onClick={() => setOpen(true)} className="rounded-full h-14 w-14 shadow-lg bg-primary text-white text-2xl flex items-center justify-center hover:shadow-xl transition-all">✦</button>
      ) : (
        <div className="w-[min(90vw,360px)] bg-white border border-panel rounded-2xl shadow-xl overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 border-b border-panel bg-surface">
            <span className="font-semibold text-secondary">System Coach</span>
            <button className="text-muted hover:text-primary" onClick={() => setOpen(false)}>Fechar</button>
          </div>
          <div className="max-h-80 overflow-auto p-4 space-y-3">
            {messages.length === 0 && (
              <div className="text-sm text-muted">Pergunte qualquer coisa sobre seu estudo. Ex: "Como revisar Matemática em 30 minutos?"</div>
            )}
            {messages.map((m, i) => (
              <div key={i} className={clsx('text-sm', m.role === 'user' ? 'text-secondary' : 'text-muted')}>
                {m.role === 'user' ? 'Você: ' : 'Coach: '} {m.content}
              </div>
            ))}
          </div>
          <div className="p-3 flex items-center gap-2">
            <input className="flex-1 border border-panel rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary" placeholder="Escreva sua pergunta..." value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && send()} />
            <button onClick={send} disabled={sending} className="px-3 py-2 rounded-lg bg-primary text-white disabled:opacity-50">Enviar</button>
          </div>
        </div>
      )}
    </div>
  );
}
