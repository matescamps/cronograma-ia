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

  const currentPeriod = useMemo(() => {
    const hour = new Date().getHours();
    if (hour < 12) return 'Manhã';
    if (hour < 18) return 'Tarde';
    return 'Noite';
  }, []);

  useEffect(() => {
    if (user) {
      const fetchTasks = async () => {
        setLoading(true);
        setError(null);
        try {
          const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';
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
    }
  }, [user]);

  if (!user) return <LoginScreen onLogin={setUser} />;

  return (
    <main className="max-w-5xl mx-auto p-4 md:p-8 animate-fade-in">
      <Header user={user} onLogout={() => setUser(null)} />
      {loading && <StatusDisplay message="Sincronizando com o satélite de missões..." />}
      {error && <StatusDisplay message={`ERRO DE CONEXÃO: ${error}`} isError />}
      {!loading && !error && (
        <MissionControl tasks={tasks} period={currentPeriod} />
      )}
    </main>
  );
}

const LoginScreen = ({ onLogin }: { onLogin: (user: string) => void }) => (
  <div className="flex items-center justify-center min-h-screen">
    <div className="bg-surface p-8 rounded-lg shadow-2xl text-center w-full max-w-sm animate-fade-in">
      <h1 className="text-3xl font-bold text-white mb-2">FOCUS OS</h1>
      <p className="text-muted mb-6">Autenticação de Operador</p>
      <div className="space-y-4">
        <button onClick={() => onLogin('Ana')} className="w-full bg-primary/20 text-primary border border-primary/50 font-bold py-3 px-6 rounded-lg transition-transform transform hover:scale-105 hover:bg-primary/30">OPERADORA ANA</button>
        <button onClick={() => onLogin('Mateus')} className="w-full bg-primary/20 text-primary border border-primary/50 font-bold py-3 px-6 rounded-lg transition-transform transform hover:scale-105 hover:bg-primary/30">OPERADOR MATEUS</button>
      </div>
    </div>
  </div>
);

const Header = ({ user, onLogout }: { user: string; onLogout: () => void }) => (
  <header className="flex justify-between items-center mb-8">
    <div>
      <h1 className="text-2xl font-bold text-white">Painel de Comando</h1>
      <p className="text-muted">Operador: {user}</p>
    </div>
    <button onClick={onLogout} className="text-muted hover:text-primary transition-colors">Logout</button>
  </header>
);

const StatusDisplay = ({ message, isError = false }: { message: string; isError?: boolean }) => (
  <div className={clsx("text-center p-8 bg-surface rounded-lg", isError ? "text-red-500" : "text-muted")}>
    {message}
  </div>
);

const MissionControl = ({ tasks, period }: { tasks: Task[]; period: string }) => {
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

  return <MissionCard subject={subject} activity={activity} />;
};

const MissionCard = ({ subject, activity }: { subject: string; activity: string }) => {
  const [advice, setAdvice] = useState<CoachAdvice | null>(null);
  const [loading, setLoading] = useState(true);

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

  return (
    <div className="bg-surface border border-panel rounded-lg p-6">
      <h2 className="text-3xl font-extrabold text-white mb-1">{subject}</h2>
      <p className="text-primary text-lg mb-6">{activity}</p>

      {loading && <div className="text-center p-4 bg-panel rounded-md text-muted animate-pulse">Recebendo transmissão do System Coach...</div>}
      {advice && (
        <div className="space-y-6">
          <div className="border-l-4 border-primary pl-4">
            <h3 className="font-semibold text-white mb-2">PLANO DE AÇÃO TÁTICO</h3>
            <p className="text-muted">{advice.summary}</p>
          </div>
          <div>
            <h3 className="font-semibold text-white mb-3">FLASHCARDS DE RECONHECIMENTO</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {advice.flashcards.map((card, i) => <Flashcard key={i} front={card.q} back={card.a} />)}
            </div>
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
        <div className="absolute w-full h-full backface-hidden flex items-center justify-center p-4 rounded-lg bg-panel text-center cursor-pointer">
          <p>{front}</p>
        </div>
        <div className="absolute w-full h-full backface-hidden flex items-center justify-center p-4 rounded-lg bg-primary text-base text-center cursor-pointer rotate-y-180">
          <p className="font-semibold">{back}</p>
        </div>
      </div>
    </div>
  );
};
