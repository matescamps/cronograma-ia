"use client";

import Starfield from "./Starfield";
import useToasts from "./Toast";

export default function ClientRoot({ children }: { children: React.ReactNode }) {
  const { Toasts } = useToasts();
  return (
    <>
      {/* Keep starfield subtle to avoid overpowering white screens */}
      <Starfield />
      <div className="min-h-screen">
        {children}
      </div>
      <Toasts />
    </>
  );
}
