/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        /* Warm dark slate — base surfaces */
        slate: {
          950: '#0c0d12',
          900: '#111318',
          800: '#1a1d26',
          700: '#22262f',
          600: '#2d3240',
        },
        /* Teal — primary water accent */
        teal: {
          300: '#5eead4',
          400: '#2dd4bf',
          500: '#14b8a6',
          600: '#0d9488',
        },
        /* Violet — AI / smart accent */
        violet: {
          300: '#c4b5fd',
          400: '#a78bfa',
          500: '#8b5cf6',
        },
        /* Keep primary as teal for legacy module page classes */
        primary: {
          50:  'rgba(20,184,166,0.06)',
          100: 'rgba(20,184,166,0.1)',
          200: '#99f6e4',
          300: '#5eead4',
          400: '#2dd4bf',
          500: '#14b8a6',
          600: '#0d9488',
          700: '#0f766e',
          800: '#115e59',
          900: '#134e4a',
        },
      },
      fontFamily: {
        sans:    ['Inter', 'system-ui', 'sans-serif'],
        display: ["'Space Grotesk'", "'Inter'", 'sans-serif'],
      },
      animation: {
        'mesh':       'mesh-drift 14s ease-in-out infinite',
        'mesh-slow':  'mesh-drift 20s ease-in-out infinite reverse',
        'rise':       'rise 0.55s cubic-bezier(0.22,1,0.36,1) both',
        'fade':       'fade-in 0.4s ease both',
        'glow-teal':  'glow-teal 3s ease-in-out infinite',
        'ping-sm':    'ping-sm 2s cubic-bezier(0,0,0.2,1) infinite',
        'ticker':     'ticker 0.6s cubic-bezier(0.22,1,0.36,1) both',
        /* Keep legacy names used by SmartDatasheetExtractor */
        'scan-beam':  'scan-beam 2.2s linear infinite',
        'discovery':  'discovery-in 0.3s ease both',
        'fade-in-up': 'fadeInUp 0.5s ease both',
        'fade-in':    'fadeIn 0.4s ease both',
        'spin-slow':  'spin-slow 3s linear infinite',
        'float':      'float 3s ease-in-out infinite',
        'glow':       'glow-legacy 2s ease-in-out infinite',
        'pulse-ring': 'pulse-ring 2s infinite',
      },
      keyframes: {
        'mesh-drift': {
          '0%,100%': { transform: 'translate(0,0) scale(1)' },
          '33%':      { transform: 'translate(40px,-30px) scale(1.08)' },
          '66%':      { transform: 'translate(-25px,20px) scale(0.96)' },
        },
        'rise': {
          from: { opacity:'0', transform:'translateY(20px)' },
          to:   { opacity:'1', transform:'translateY(0)' },
        },
        'fade-in': {
          from: { opacity:'0' },
          to:   { opacity:'1' },
        },
        'glow-teal': {
          '0%,100%': { boxShadow:'0 0 0 0 rgba(20,184,166,0)' },
          '50%':      { boxShadow:'0 0 0 8px rgba(20,184,166,0.1)' },
        },
        'ping-sm': {
          '75%,100%': { transform:'scale(1.6)', opacity:'0' },
        },
        'ticker': {
          from: { opacity:'0', transform:'translateY(10px)' },
          to:   { opacity:'1', transform:'translateY(0)' },
        },
        /* Legacy */
        'fadeInUp':    { from:{opacity:'0',transform:'translateY(16px)'}, to:{opacity:'1',transform:'translateY(0)'} },
        'fadeIn':      { from:{opacity:'0'}, to:{opacity:'1'} },
        'float':       { '0%,100%':{transform:'translateY(0)'}, '50%':{transform:'translateY(-6px)'} },
        'glow-legacy': { '0%,100%':{boxShadow:'0 0 8px rgba(20,184,166,0.25)'}, '50%':{boxShadow:'0 0 28px rgba(20,184,166,0.5)'} },
        'pulse-ring':  { '0%':{transform:'scale(0.95)',boxShadow:'0 0 0 0 rgba(20,184,166,0.4)'}, '70%':{transform:'scale(1)',boxShadow:'0 0 0 10px rgba(20,184,166,0)'}, '100%':{transform:'scale(0.95)',boxShadow:'0 0 0 0 rgba(20,184,166,0)'} },
        'scan-beam':   { '0%':{top:'-3px',opacity:'0'}, '5%':{opacity:'1'}, '92%':{opacity:'1'}, '100%':{top:'calc(100% + 3px)',opacity:'0'} },
        'discovery-in':{ from:{opacity:'0',transform:'translateX(-12px)'}, to:{opacity:'1',transform:'translateX(0)'} },
        'spin-slow':   { from:{transform:'rotate(0deg)'}, to:{transform:'rotate(360deg)'} },
        'progress-fill':{ from:{width:'0%'}, to:{width:'var(--progress-width)'} },
        'node-orbit':  { from:{transform:'rotate(0deg) translateX(36px) rotate(0deg)'}, to:{transform:'rotate(360deg) translateX(36px) rotate(-360deg)'} },
      },
      transitionTimingFunction: {
        'spring': 'cubic-bezier(0.22, 1, 0.36, 1)',
      },
    },
  },
  plugins: [],
}
