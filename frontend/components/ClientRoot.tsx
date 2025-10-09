"use client";

import Starfield from "./Starfield";
import useToasts from "./Toast";

export default function ClientRoot({ children }: { children: React.ReactNode }) {
  const { Toasts } = useToasts();
  return (
    <>
      <Starfield />
      {children}
      <Toasts />
    </>
  );
}
