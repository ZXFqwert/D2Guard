/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        guard: {
          bg: '#0d1117',
          surface: '#161b22',
          border: '#30363d',
          accent: '#58a6ff',
          success: '#238636',
          warning: '#d29922',
          danger: '#f85149',
          purple: '#a371f7',
          cyan: '#39c5bb',
        }
      },
      fontFamily: {
        mono: ['Fira Code', 'JetBrains Mono', 'Consolas', 'monospace'],
      }
    },
  },
  plugins: [],
}
