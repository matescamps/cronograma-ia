import './globals.css'
import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import ClientRoot from '../components/ClientRoot'

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'Cronograma A&M — Focus OS',
  description: 'Sistema de Foco com IA integrado ao Cronograma A&M',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR" suppressHydrationWarning>
      <body className={`${inter.className} min-h-screen bg-surface text-secondary antialiased`}>
        <ClientRoot>
          {children}
        </ClientRoot>
      </body>
    </html>
  )
}
