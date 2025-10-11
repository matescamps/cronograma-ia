import type { AppProps } from 'next/app';
import { ThemeProvider } from 'styled-components';
import { Inter } from 'next/font/google';
import '../styles/global.scss';
import ClientRoot from '../components/ClientRoot';

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

export default function App({ Component, pageProps }: AppProps) {
  return (
    <ThemeProvider theme={theme}>
      <div className={inter.className}>
        <ClientRoot>
          <Component {...pageProps} />
        </ClientRoot>
      </div>
    </ThemeProvider>
  );
}
