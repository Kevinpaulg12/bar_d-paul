/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./templates/**/*.html",
    "./apps/**/templates/**/*.html",
    "./static/**/*.js",
    "./static/**/*.css",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        dark: {
          900: "#0f172a",
          800: "#1e293b",
          700: "#334155",
        },
        brand: {
          500: "#22c55e",
          600: "#16a34a",
        },
      },
    },
  },
  plugins: [],
}
