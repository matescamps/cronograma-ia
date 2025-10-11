'use client';

import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useFocusOSStore } from '@/store/store';

interface OracleBriefing {
  message: string;
  tactical_focus: string[];
  performance_insight: string;
  completion_estimate: number;
}

export default function GreetingPopup() {
  const [briefing, setBriefing] = useState<OracleBriefing | null>(null);
  const [isVisible, setIsVisible] = useState(true);
  const { user, currentTask } = useFocusOSStore();

  useEffect(() => {
    const fetchBriefing = async () => {
      if (!currentTask) return;
      
      try {
        if (!currentTask || !currentTask.subject) {
          console.error('Tarefa atual inválida');
          return;
        }

        const apiUrl = process.env.NEXT_PUBLIC_API_URL;
        if (!apiUrl) {
          console.error('API URL não configurada');
          return;
        }

        const response = await fetch(`${apiUrl}/oracle/briefing`, {
          method: 'POST',
          headers: { 
            'Content-Type': 'application/json',
            'X-Focus-Token': process.env.NEXT_PUBLIC_API_TOKEN || ''
          },
          body: JSON.stringify({
            subject: currentTask.subject,
            activity: currentTask.activity || '',
            difficulty: currentTask['Dificuldade (1-5)'] || 3,
            comment: currentTask['Alerta/Comentário'] || '',
            priority: currentTask['Prioridade'] || 'Normal'
          })
        });
        
        if (!response.ok) {
          throw new Error(`Falha ao buscar briefing: ${response.status}`);
        }
        
        const data: OracleBriefing = await response.json();
        setBriefing(data);
      } catch (error: unknown) {
        console.error(
          'Erro ao buscar briefing:',
          error instanceof Error ? error.message : 'Erro desconhecido'
        );
        setBriefing(null);
      }
    };

    fetchBriefing();
  }, [currentTask]);

  if (!isVisible || !briefing) return null;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: 50 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -50 }}
        className="fixed inset-x-4 top-4 z-50 max-w-4xl mx-auto"
      >
        <div className="relative bg-gradient-to-br from-primary/10 to-secondary/10 backdrop-blur-xl 
          rounded-xl p-6 shadow-2xl border border-primary/20">
          <button
            onClick={() => setIsVisible(false)}
            className="absolute top-4 right-4 text-primary hover:text-white 
              transition-colors"
          >
            ×
          </button>

          <div className="space-y-6">
            <header className="space-y-2">
              <h2 className="text-2xl font-bold text-primary">
                Briefing do Oráculo AI
              </h2>
              <p className="text-lg text-secondary">
                {briefing.message}
              </p>
            </header>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div className="space-y-2">
                <h3 className="font-semibold text-primary">Focos Táticos</h3>
                <ul className="space-y-2">
                  {briefing.tactical_focus.map((focus, index) => (
                    <motion.li
                      key={index}
                      initial={{ opacity: 0, x: -20 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: index * 0.1 }}
                      className="flex items-center gap-2 text-secondary"
                    >
                      <span className="text-xs">◆</span>
                      {focus}
                    </motion.li>
                  ))}
                </ul>
              </div>

              <div>
                <h3 className="font-semibold text-primary mb-2">Análise de Performance</h3>
                <p className="text-secondary">{briefing.performance_insight}</p>
              </div>

              <div className="text-center">
                <h3 className="font-semibold text-primary mb-2">Estimativa de Conclusão</h3>
                <div className="relative inline-flex items-center justify-center">
                  <svg className="w-24 h-24">
                    <circle
                      className="text-surface"
                      strokeWidth="8"
                      stroke="currentColor"
                      fill="transparent"
                      r="40"
                      cx="48"
                      cy="48"
                    />
                    <circle
                      className="text-primary"
                      strokeWidth="8"
                      strokeDasharray={251.2}
                      strokeDashoffset={251.2 * (1 - briefing.completion_estimate / 100)}
                      strokeLinecap="round"
                      stroke="currentColor"
                      fill="transparent"
                      r="40"
                      cx="48"
                      cy="48"
                    />
                  </svg>
                  <span className="absolute text-2xl font-bold text-primary">
                    {briefing.completion_estimate}%
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}