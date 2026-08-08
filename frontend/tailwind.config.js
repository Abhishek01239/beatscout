/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: {
          950: "#0a0c14",
          900: "#10131e",
          800: "#171b2a",
          700: "#212636",
        },
        accent: {
          DEFAULT: "#6d5ef2",
          dim: "#4a3fd0",
          soft: "#a79bf7",
        },
        mint: "#34d399",
        warn: "#fbbf24",
        danger: "#f87171",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};