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
      <head>
        <meta charSet="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
        <meta name="color-scheme" content="light dark" />
        <link rel="stylesheet" href="/_next/static/css/app.css" precedence="default" />
      </head>
      <body className={`${inter.className} min-h-screen bg-surface text-secondary antialiased`} suppressHydrationWarning>
        <script
          dangerouslySetInnerHTML={{
            __html: `
              try {
                if (localStorage.theme === 'dark' || (!('theme' in localStorage) && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
                  document.documentElement.classList.add('dark')
                } else {
                  document.documentElement.classList.remove('dark')
                }
              } catch (_) {}
            `,
          }}
        />
        <ClientRoot>
          {children}
        </ClientRoot>
      </body>
    </html>
  )
}
