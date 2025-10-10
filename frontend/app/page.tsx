'use client';

import { useState, useEffect, useMemo } from 'react';
import clsx from 'clsx';
import ProgressEditor from '../components/ProgressEditor';
import MetaEditor from '../components/MetaEditor';
import Pomodoro from '../components/Pomodoro';
import Quiz from '../components/Quiz';
import HistoryChart from '../components/HistoryChart';
import CommandBar from '../components/CommandBar';
import LevelBadge from '../components/LevelBadge';
import AssistantAvatar from '../components/AssistantAvatar';
import GreetingPopup from '../components/GreetingPopup';
import Confetti from '../components/Confetti';
import AssistantDock from '../components/AssistantDock';
import useToasts from '../components/Toast';

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
  const { Toasts } = useToasts();
  const [user, setUser] = useState<string | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [streakDays, setStreakDays] = useState<number>(0);
  const [xp, setXp] = useState<number>(0);
  const [insights, setInsights] = useState<string | null>(null);
  const [burst, setBurst] = useState(0);
  const [commandOpen, setCommandOpen] = useState(false);
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    if (typeof window === 'undefined') return 'light';
    const stored = localStorage.getItem('focus_theme') as 'light' | 'dark' | null;
    if (stored) return stored;
    const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    return prefersDark ? 'dark' : 'light';
  });
  useEffect(() => { document.documentElement.dataset.theme = theme; localStorage.setItem('focus_theme', theme); }, [theme]);

  const currentPeriod = useMemo(() => {
    const hour = new Date().getHours();
    if (hour < 12) return 'Manhã';
    if (hour < 18) return 'Tarde';
    return 'Noite';
  }, []);

  useEffect(() => {
    const stored = Number(localStorage.getItem('focus_streak') || '0');
    setStreakDays(stored);
    const storedUser = localStorage.getItem('focus_user');
    if (storedUser) setUser(storedUser);
    setXp(Number(localStorage.getItem('focus_xp') || '0'));
  }, []);

  useEffect(() => {
    if (user) {
      localStorage.setItem('focus_user', user);
      const fetchTasks = async () => {
        setLoading(true);
        setError(null);
        try {
          const response = await fetch(`${apiUrl}/tasks/${user}`);
          if (!response.ok) {
            const errData = await response.json();
            throw new Error(errData.detail || 'Falha ao buscar missões.');
          }
          setTasks(await response.json());
        } catch (err) {
          setError(err instanceof Error ? err.message : 'Um erro inesperado ocorreu.');
        } finally {
          setLoading(false);
        }
      };
      fetchTasks();

      const fetchSummary = async () => {
        try {
          const r = await fetch(`${apiUrl}/summary/${user}`);
          const d = await r.json();
          setInsights(d?.insights || null);
        } catch {
          setInsights(null);
        }
      };
      fetchSummary();
    }
  }, [user, apiUrl]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setCommandOpen((o) => !o);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const refreshXp = () => setXp(Number(localStorage.getItem('focus_xp') || '0'));

  const onNavigate = (sectionId: string) => {
    const el = document.getElementById(sectionId);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
      // Sub-actions
      if (sectionId === 'quiz-section') {
        // no-op; user can click Gerar
      }
    }
  };

  if (!user) return <LoginScreen onLogin={(u) => { setUser(u); localStorage.setItem('focus_user', u); }} />;

  return (
    <main className="max-w-5xl mx-auto p-4 md:p-8 animate-fade-in">
      <GreetingPopup user={user} tasks={tasks as any} currentPeriod={currentPeriod as any} apiUrl={apiUrl} />
      <Header user={user} streakDays={streakDays} xp={xp} onLogout={() => { setUser(null); localStorage.removeItem('focus_user'); }} />
      <CommandBar open={commandOpen} setOpen={setCommandOpen} onNavigate={onNavigate} onToggleTheme={() => setTheme(t => t === 'light' ? 'dark' : 'light')} />
      <div className="mb-6 glass rounded-2xl p-4 flex items-start justify-between gap-4 tilt">
        <div className="flex-1">
          <h3 className="font-semibold text-secondary mb-1">Insights do Dia</h3>
          <p className="text-muted">{insights || 'Sem dados por enquanto.'}</p>
        </div>
        <AssistantAvatar thinking={loading} />
      </div>
      {loading && <StatusDisplay message="Sincronizando com o satélite de missões..." />}
      {error && <StatusDisplay message={`ERRO DE CONEXÃO: ${error}`} isError />}
      {!loading && !error && (
        <MissionControl tasks={tasks} period={currentPeriod} onComplete={() => { 
          incrementStreak(setStreakDays); refreshXp(); setBurst((b) => b + 1);
          // Toast achievement
          const evt = new CustomEvent('focusos:toast', { detail: { id: `done-${Date.now()}`, title: 'Missão concluída', description: '+10 XP e +1 streak', type: 'success' } });
          // @ts-ignore
          window.dispatchEvent(evt);
        }} apiUrl={apiUrl} user={user} onXpChange={refreshXp} />
      )}
      {!loading && !error && (
        <div className="mt-8 grid grid-cols-1 gap-6">
          <Quiz id="quiz-section" user={user} subject={tasks?.[0]?.[`Matéria (${currentPeriod})` as keyof Task] as any} apiUrl={apiUrl} />
          <HistoryChart id="history-section" user={user} apiUrl={apiUrl} />
        </div>
      )}
      <Confetti burst={burst} />
      <AssistantDock apiUrl={apiUrl} />
      <Toasts />
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

const Header = ({ user, streakDays, xp, onLogout }: { user: string; streakDays: number; xp: number; onLogout: () => void }) => (
  <header className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 mb-8">
    <div>
      <h1 className="text-2xl font-extrabold text-secondary">Boa tarde, {user}.</h1>
      <div className="flex items-center gap-3 text-sm mt-1">
        <StatusPill label="Planilha" colorClass="bg-success" stateKey="sheet" />
        <StatusPill label="IA" colorClass="bg-success" stateKey="ia" />
        <div className="flex items-center gap-3 text-muted">
          <div className="flex items-center gap-1">
            <span>🔥</span>
            <span>Sequência:</span>
            <span className="font-semibold text-secondary">{streakDays}d</span>
          </div>
          <LevelBadge xp={xp} />
        </div>
        <kbd className="ml-2 px-2 py-0.5 rounded bg-surface border border-panel text-xs">Ctrl/⌘+K</kbd>
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

const MissionControl = ({ tasks, period, onComplete, apiUrl, user, onXpChange }: { tasks: Task[]; period: string; onComplete: () => void; apiUrl: string; user: string; onXpChange: () => void }) => {
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
  const subject = task[`Matéria (${activePeriod})` as keyof Task];
  const activity = task[`Atividade Detalhada (${activePeriod})` as keyof Task];

  return <MissionCard subject={subject} activity={activity} onComplete={onComplete} apiUrl={apiUrl} user={user} onXpChange={onXpChange} />;
};

const MissionCard = ({ subject, activity, onComplete, apiUrl, user, onXpChange }: { subject: string; activity: string; onComplete: () => void; apiUrl: string; user: string; onXpChange: () => void }) => {
  const [advice, setAdvice] = useState<CoachAdvice | null>(null);
  const [loading, setLoading] = useState(true);
  const [progress, setProgress] = useState<number>(0);

  useEffect(() => {
    const fetchAdvice = async () => {
      setLoading(true);
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
    <div className="glass border border-panel rounded-2xl p-6 shadow-md">
      <h2 className="text-3xl font-extrabold text-secondary mb-1">{subject}</h2>
      <p className="text-primary text-lg mb-4">{activity}</p>

      <div className="h-2 w-full bg-panel rounded-full overflow-hidden mb-6">
        <div className="h-full bg-primary transition-all" style={{ width: `${progress}%` }} />
      </div>

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
          <div className="grid grid-cols-1 gap-6">
            <ProgressEditor id="progress-section" user={user} apiUrl={apiUrl} />
            <MetaEditor id="meta-section" user={user} apiUrl={apiUrl} />
            <Pomodoro id="pomodoro-section" onFocusComplete={() => { onXpChange(); }} />
          </div>
      <div className="flex flex-col sm:flex-row gap-3 sm:items-center sm:justify-between pt-2">
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
      <div className={clsx("relative w-full h-full transform-style-3d transition-transform duration-700", isFlipped && "rotate-y-180")}> 
        <div className="absolute w-full h-full backface-hidden flex items-center justify-center p-4 rounded-xl bg-surface border border-panel text-center cursor-pointer shadow-sm hover:shadow-md transition-all">
          <p className="text-secondary">{front}</p>
        </div>
        <div className="absolute w-full h-full backface-hidden flex items-center justify-center p-4 rounded-xl bg-primary text-white text-center cursor-pointer rotate-y-180 shadow-md">
          <p className="font-semibold">{back}</p>
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
  const [online, setOnline] = useState<boolean>(true);
  useEffect(() => {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';
    fetch(`${apiUrl}/status`).then(r => r.json()).then((s) => {
      setOnline(Boolean(s?.[stateKey]?.online));
    }).catch(() => setOnline(false));
  }, [stateKey]);
  return (
    <span className={clsx('inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs', 'bg-surface border border-panel text-muted')}>
      <span className={clsx('h-2 w-2 rounded-full', online ? colorClass : 'bg-red-500')} />
      <span>{label}: {online ? 'Online' : 'Offline'}</span>
    </span>
  );
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
