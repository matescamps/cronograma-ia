import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: [
    './components/**/*.{ts,tsx}',
    './app/**/*.{ts,tsx}',
    './features/**/*.{ts,tsx}',
    './store/**/*.{ts,tsx}',
  ],
  prefix: "",
  important: true,
  theme: {
    container: {
      center: true,
      padding: "2rem",
      screens: {
        "2xl": "1400px",
      },
    },
    extend: {
      colors: {
        surface: 'rgb(var(--surface) / <alpha-value>)',
        primary: 'rgb(var(--primary) / <alpha-value>)',
        secondary: 'rgb(var(--secondary) / <alpha-value>)',
        panel: 'rgb(var(--panel) / <alpha-value>)',
        muted: 'rgb(var(--muted) / <alpha-value>)',
        success: 'rgb(var(--success) / <alpha-value>)',
      },
      fontFamily: {
        sans: ['var(--font-inter)'],
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
