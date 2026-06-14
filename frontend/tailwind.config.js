/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          50: '#e6f7ff',
          100: '#bae7ff',
          200: '#91d5ff',
          300: '#69c0ff',
          400: '#40a9ff',
          500: '#2563a8',
          600: '#1a3a5c',
          700: '#002766',
          800: '#001d66',
          900: '#001529',
        },
      },
    },
  },
  plugins: [],
}
