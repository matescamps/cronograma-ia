import type { Config } from "tailwindcss";
import defaultTheme from 'tailwindcss/defaultTheme';

const config: Config = {
  content: [
    // Arquivos da aplicação
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./features/**/*.{js,ts,jsx,tsx,mdx}",
    "./store/**/*.{js,ts,jsx,tsx}",
    // Garante que nenhum componente seja perdido
    "src/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  future: {
    hoverOnlyWhenSupported: true,
  },
  darkMode: ["class"],
  theme: {
    extend: {
      colors: {
        // Light theme palette inspired by minimalist sci-fi
        'base': '#FFFFFF', // page background
        'surface': '#F9FAFB', // cards/background sections
        'panel': '#E5E7EB', // subtle borders/panels
        'primary': '#2563EB', // electric blue accent
        'secondary': '#111827', // near-black text
        'muted': '#6B7280', // secondary text
        'success': '#10B981', // green status
      },
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        'fade-in': 'fadeIn 0.5s ease-out forwards',
      },
    },
  },
  plugins: [],
};
export default config;
