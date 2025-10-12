"use client";

import { useEffect, useState } from "react";
import clsx from "clsx";

export interface ToastMessage {
  id: string;
  title: string;
  description?: string;
  type?: "success" | "info" | "warning" | "error";
}

export default function useToasts() {
  const [toasts, setToasts] = useState<ToastMessage[]>([]);
  useEffect(() => {
    const handler = (e: CustomEvent<ToastMessage>) => {
      setToasts((t) => [{ ...e.detail }, ...t].slice(0, 5));
      setTimeout(() => dismiss(e.detail.id), 3000);
    };
    // @ts-ignore
    window.addEventListener("focusos:toast", handler as any);
    return () => {
      // @ts-ignore
      window.removeEventListener("focusos:toast", handler as any);
    };
  }, []);

  const dismiss = (id: string) => setToasts((t) => t.filter((x) => x.id !== id));

  const Toasts = () => (
    <div className="fixed top-4 right-4 z-50 space-y-2">
      {toasts.map((t) => (
        <div key={t.id} className={clsx("min-w-[220px] max-w-xs p-3 rounded-lg shadow-lg border backdrop-blur", t.type === 'success' ? 'bg-white/80 border-success/40' : 'bg-white/80 border-panel')}>
          <div className="font-semibold text-secondary">{t.title}</div>
          {t.description && <div className="text-muted text-sm">{t.description}</div>}
        </div>
      ))}
    </div>
  );

  return { Toasts };
}
