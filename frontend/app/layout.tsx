import './globals.css'
import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import ClientRoot from '../components/ClientRoot'
import Script from 'next/script'

const inter = Inter({ 
  subsets: ['latin'],
  display: 'swap',
  variable: '--font-inter',
})

export const metadata: Metadata = {
  title: 'Cronograma A&M — Focus OS',
  description: 'Sistema de Foco com IA integrado ao Cronograma A&M',
  viewport: 'width=device-width, initial-scale=1, viewport-fit=cover',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR" suppressHydrationWarning className={inter.variable}>
      <body suppressHydrationWarning>
        <div id="app-root" className="min-h-screen bg-surface text-secondary antialiased">
          <ClientRoot>{children}</ClientRoot>
        </div>
        <Script id="theme-script" strategy="beforeInteractive">
          {`
            try {
              let isDark = localStorage.theme === 'dark' || (!('theme' in localStorage) && window.matchMedia('(prefers-color-scheme: dark)').matches)
              document.documentElement.classList.toggle('dark', isDark)
              document.documentElement.style.colorScheme = isDark ? 'dark' : 'light'
            } catch (e) {}
          `}
        </Script>
      </body>
    </html>
  )
}
}
