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
          50:  'rgba(14,165,233,0.08)',
          100: 'rgba(14,165,233,0.14)',
          200: '#bae6fd',
          300: '#7dd3fc',
          400: '#38bdf8',
          500: '#0ea5e9',
          600: '#0284c7',
          700: '#0369a1',
          800: '#075985',
          900: '#0c4a6e',
        },
        ocean: {
          950: '#020d1a',
          900: '#061428',
          800: '#0a1c38',
          700: '#0d2244',
          600: '#142d5a',
          500: '#1a3a72',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      animation: {
        'water-flow':    'water-flow 8s ease-in-out infinite',
        'float-slow':    'float 6s ease-in-out infinite',
        'glow-pulse':    'glow-pulse 3s ease-in-out infinite',
        'border-flow':   'border-flow 4s linear infinite',
        'shimmer-dark':  'shimmer-dark 2s linear infinite',
        'data-pulse':    'data-pulse 2s ease-in-out infinite',
        'ripple':        'ripple 1s ease-out forwards',
        'slide-up':      'slide-up 0.5s ease both',
        'slide-right':   'slide-right 0.4s ease both',
      },
      keyframes: {
        'water-flow': {
          '0%,100%': { backgroundPosition: '0% 50%' },
          '50%':      { backgroundPosition: '100% 50%' },
        },
        'glow-pulse': {
          '0%,100%': { boxShadow: '0 0 8px rgba(14,165,233,0.2)' },
          '50%':      { boxShadow: '0 0 32px rgba(14,165,233,0.5)' },
        },
        'border-flow': {
          '0%':   { backgroundPosition: '0% 0%' },
          '100%': { backgroundPosition: '200% 0%' },
        },
        'shimmer-dark': {
          '0%':   { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
        'data-pulse': {
          '0%,100%': { opacity: '0.6', transform: 'scale(1)' },
          '50%':      { opacity: '1',   transform: 'scale(1.05)' },
        },
        'ripple': {
          '0%':   { transform: 'scale(0)', opacity: '0.6' },
          '100%': { transform: 'scale(3)', opacity: '0' },
        },
        'slide-up': {
          from: { opacity: '0', transform: 'translateY(20px)' },
          to:   { opacity: '1', transform: 'translateY(0)' },
        },
        'slide-right': {
          from: { opacity: '0', transform: 'translateX(-16px)' },
          to:   { opacity: '1', transform: 'translateX(0)' },
        },
      },
      backdropBlur: {
        xs: '2px',
      },
    },
  },
  plugins: [],
}
