"use client";

import React, { useMemo } from "react";
import clsx from "clsx";

export default function LevelBadge({ xp }: { xp: number }) {
  const level = useMemo(() => Math.floor(xp / 100) + 1, [xp]);
  const curr = xp % 100;
  const pct = Math.min(100, Math.round((curr / 100) * 100));
  return (
    <div className="flex items-center gap-3 select-none" title={`XP ${xp} • Nível ${level}`}>
      <div className="relative h-10 w-10 rounded-full bg-gradient-to-br from-primary/80 to-primary shadow-[0_0_20px_rgba(37,99,235,0.35)]">
        <div className="absolute inset-1 rounded-full bg-white flex items-center justify-center text-secondary text-sm font-semibold">
          {level}
        </div>
      </div>
      <div className="w-36">
        <div className="text-xs text-muted">Nível {level}</div>
        <div className="h-2 w-full bg-panel rounded-full overflow-hidden">
          <div className="h-full bg-primary transition-all" style={{ width: `${pct}%` }} />
        </div>
      </div>
    </div>
  );
}
