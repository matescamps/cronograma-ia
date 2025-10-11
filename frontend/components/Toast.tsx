'use client';

import { useEffect, useState, useCallback } from 'react';
import styled from 'styled-components';

const ToastContainer = styled.div`
  position: fixed;
  bottom: 1rem;
  right: 1rem;
  z-index: 50;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
`;

const ToastItem = styled.div<{ $type?: string }>`
  min-width: 220px;
  max-width: 20rem;
  padding: 0.75rem;
  border-radius: 0.5rem;
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
  border: 1px solid ${props => props.$type === "success" ? "var(--success-color)" : "var(--panel-color)"};
  background-color: rgba(255, 255, 255, 0.8);
  backdrop-filter: blur(8px);
`;

const ToastTitle = styled.div`
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--secondary-color);
`;

const ToastDescription = styled.div`
  font-size: 0.75rem;
  margin-top: 0.25rem;
  color: var(--muted-color);
`;

export interface ToastMessage {
  id: string;
  title: string;
  description?: string;
  type?: "success" | "info" | "warning" | "error";
}

export default function useToasts() {
  const [messages, setMessages] = useState<ToastMessage[]>([]);

  const dismissToast = useCallback((id: string) => {
    setMessages(prev => prev.filter(msg => msg.id !== id));
  }, []);

  useEffect(() => {
    const handleToast = (e: CustomEvent<ToastMessage>) => {
      setMessages(prev => [{ ...e.detail }, ...prev].slice(0, 5));
      setTimeout(() => dismissToast(e.detail.id), 3000);
    };

    window.addEventListener("toast" as any, handleToast as any);
    return () => window.removeEventListener("toast" as any, handleToast as any);
  }, [dismissToast]);

  const Toast = useCallback(() => {
    if (messages.length === 0) return null;

    return (
      <ToastContainer>
        {messages.map(msg => (
          <ToastItem key={msg.id} $type={msg.type}>
            <ToastTitle>{msg.title}</ToastTitle>
            {msg.description && (
              <ToastDescription>{msg.description}</ToastDescription>
            )}
          </ToastItem>
        ))}
      </ToastContainer>
    );
  }, [messages]);

  return { Toast };
}