import styled, { ThemeProvider } from 'styled-components';
import { Inter } from 'next/font/google';
import type { Metadata } from 'next';
import '../styles/global.scss';
import ClientRoot from '../components/ClientRoot';
import StyledComponentsRegistry from './registry';

const inter = Inter({ subsets: ['latin'] });

const AppRoot = styled.div`
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background-color: var(--surface-color);
  color: var(--secondary-color);
  transition: background-color 0.3s ease, color 0.3s ease;
`;

const Main = styled.main`
  flex: 1;
  width: 100%;
  max-width: 1280px;
  margin: 0 auto;
  padding: 2rem 1rem;
`;

const theme = {
  colors: {
    primary: 'var(--primary-color)',
    surface: 'var(--surface-color)',
    panel: 'var(--panel-color)',
    secondary: 'var(--secondary-color)',
    muted: 'var(--muted-color)',
    success: 'var(--success-color)',
  },
};

export const metadata: Metadata = {
  title: 'Cronograma A&M — Focus OS',
  description: 'Sistema de Foco com IA integrado ao Cronograma A&M',
  viewport: 'width=device-width, initial-scale=1, viewport-fit=cover',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR" suppressHydrationWarning>
      <head>
        <meta charSet="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <script
          dangerouslySetInnerHTML={{
            __html: `
              try {
                const isDark = localStorage.theme === 'dark' || (!('theme' in localStorage) && window.matchMedia('(prefers-color-scheme: dark)').matches);
                document.documentElement.setAttribute('data-theme', isDark ? 'dark' : 'light');
              } catch (e) {}
            `,
          }}
        />
      </head>
      <body className={inter.className}>
        <StyledComponentsRegistry>
          <ThemeProvider theme={theme}>
            <AppRoot>
              <Main>
                <ClientRoot>{children}</ClientRoot>
              </Main>
            </AppRoot>
          </ThemeProvider>
        </StyledComponentsRegistry>
      </body>
    </html>
  );
}
}
}
