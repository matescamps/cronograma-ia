"use client";

import { useEffect, useRef } from "react";

export default function Starfield() {
  const ref = useRef<HTMLCanvasElement | null>(null);
  useEffect(() => {
    const canvas = ref.current; if (!canvas) return;
    const ctx = canvas.getContext('2d'); if (!ctx) return;
    let raf = 0; const dpr = window.devicePixelRatio || 1;
    const resize = () => { canvas.width = innerWidth * dpr; canvas.height = innerHeight * dpr; };
    resize();
    const stars = Array.from({ length: 140 }, () => ({ x: Math.random() * canvas.width, y: Math.random() * canvas.height, z: Math.random() * 0.8 + 0.2 }));
    const tick = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      for (const s of stars) {
        s.y += 0.3 * s.z * dpr; if (s.y > canvas.height) s.y = 0;
        const size = (1.2 + s.z * 1.8) * dpr;
        ctx.globalAlpha = 0.6 + s.z * 0.4; ctx.fillStyle = '#9ec1ff';
        ctx.fillRect(s.x, s.y, size, size);
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    const onResize = () => resize();
    addEventListener('resize', onResize);
    return () => { cancelAnimationFrame(raf); removeEventListener('resize', onResize); };
  }, []);
  return <canvas ref={ref} className="fixed inset-0 -z-10 opacity-60" aria-hidden="true" />;
}
