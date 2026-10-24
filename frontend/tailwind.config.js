/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          50: "#f6f7f9",
          100: "#eceef2",
          200: "#d5dae2",
          300: "#b0bac9",
          400: "#8593a9",
          500: "#66748c",
          600: "#515d74",
          700: "#424c5f",
          800: "#394151",
          900: "#1f2430",
          950: "#141821"
        },
        signal: {
          400: "#5b9bd5",
          500: "#3b7fc4",
          600: "#2f66a3"
        },
        amberish: {
          400: "#e0a63b",
          500: "#c98d1e",
          600: "#a97415"
        }
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"]
      }
    }
  },
  plugins: []
};
