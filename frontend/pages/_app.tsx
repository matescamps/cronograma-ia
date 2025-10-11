import type { AppProps } from 'next/app';
import { ThemeProvider } from 'styled-components';
import { Inter } from 'next/font/google';
import '../styles/global.scss';
import ClientRoot from '../components/ClientRoot';
import styled from 'styled-components';

const inter = Inter({ subsets: ['latin'] });

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

const AppContainer = styled.div`
  min-height: 100vh;
  background-color: var(--surface-color);
  color: var(--secondary-color);
`;

const MainContent = styled.main`
  max-width: 1280px;
  margin: 0 auto;
  padding: 2rem;
`;

export default function App({ Component, pageProps }: AppProps) {
  return (
    <ThemeProvider theme={theme}>
      <AppContainer className={inter.className}>
        <ClientRoot>
          <MainContent>
            <Component {...pageProps} />
          </MainContent>
        </ClientRoot>
      </AppContainer>
    </ThemeProvider>
  );
}
