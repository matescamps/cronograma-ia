"use client";

import { useEffect, useRef } from "react";

export default function Confetti({ burst }: { burst: number }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let raf = 0;
    let running = true;
    const dpr = window.devicePixelRatio || 1;

    const resize = () => {
      canvas.width = Math.floor(window.innerWidth * dpr);
      canvas.height = Math.floor(window.innerHeight * dpr);
    };
    resize();

    const colors = ["#2563EB", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6"];

    type Particle = { x: number; y: number; vx: number; vy: number; size: number; color: string; life: number };
    const particles: Particle[] = [];
    const count = 120;
    for (let i = 0; i < count; i++) {
      const angle = Math.random() * Math.PI * 2;
      const speed = 2 + Math.random() * 4;
      particles.push({
        x: canvas.width / 2,
        y: canvas.height / 3,
        vx: Math.cos(angle) * speed,
        vy: Math.sin(angle) * speed - 2,
        size: 2 + Math.random() * 3,
        color: colors[Math.floor(Math.random() * colors.length)],
        life: 60 + Math.random() * 60,
      });
    }

    const tick = () => {
      if (!running) return;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      for (const p of particles) {
        p.x += p.vx;
        p.y += p.vy;
        p.vy += 0.08 * dpr; // gravity
        p.vx *= 0.99;
        p.vy *= 0.99;
        p.life -= 1;

        ctx.globalAlpha = Math.max(0, Math.min(1, p.life / 60));
        ctx.fillStyle = p.color;
        ctx.fillRect(p.x, p.y, p.size * dpr, p.size * dpr);
      }
      // Remove dead
      for (let i = particles.length - 1; i >= 0; i--) {
        if (particles[i].life <= 0) particles.splice(i, 1);
      }
      raf = requestAnimationFrame(tick);
    };

    raf = requestAnimationFrame(tick);

    const stopTimeout = setTimeout(() => {
      running = false;
      cancelAnimationFrame(raf);
      const c = canvasRef.current; if (c) { const ctx2 = c.getContext("2d"); ctx2?.clearRect(0, 0, c.width, c.height); }
    }, 1800);

    window.addEventListener("resize", resize);
    return () => {
      running = false;
      cancelAnimationFrame(raf);
      clearTimeout(stopTimeout);
      window.removeEventListener("resize", resize);
    };
  }, [burst]);

  return (
    <canvas ref={canvasRef} className="pointer-events-none fixed inset-0 z-50" />
  );
}
