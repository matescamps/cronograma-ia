"use client";

import { useEffect, useState } from "react";
import clsx from "clsx";

export default function AssistantAvatar({ thinking }: { thinking: boolean }) {
  const [dots, setDots] = useState(0);
  useEffect(() => {
    if (!thinking) return;
    const id = setInterval(() => setDots((d) => (d + 1) % 4), 400);
    return () => clearInterval(id);
  }, [thinking]);
  return (
    <div className="flex items-center gap-3">
      <div className={clsx("h-10 w-10 rounded-full bg-gradient-to-br from-primary/80 to-primary shadow-[0_0_12px_rgba(37,99,235,0.35)]")}></div>
      <div className="text-muted text-sm">{thinking ? `digitando${".".repeat(dots)}` : "pronto"}</div>
    </div>
  );
}
