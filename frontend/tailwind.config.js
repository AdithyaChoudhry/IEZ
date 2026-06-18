/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        primary: {
          50:  'rgba(16,185,129,0.06)',
          100: 'rgba(16,185,129,0.1)',
          200: '#a7f3d0',
          300: '#6ee7b7',
          400: '#34d399',
          500: '#10b981',
          600: '#059669',
          700: '#047857',
          800: '#065f46',
          900: '#064e3b',
        },
      },
      fontFamily: {
        sans:    ['Inter', 'system-ui', 'sans-serif'],
        display: ["'Space Grotesk'", 'sans-serif'],
      },
      animation: {
        'mesh':      'mesh-drift 16s ease-in-out infinite',
        'mesh-b':    'mesh-drift 22s ease-in-out infinite reverse',
        'mesh-c':    'mesh-drift 19s ease-in-out 7s infinite',
        'rise':      'rise 0.5s cubic-bezier(0.22,1,0.36,1) both',
        'fade':      'fade-in 0.35s ease both',
        'ping-dot':  'ping-sm 2.2s cubic-bezier(0,0,0.2,1) infinite',
        /* SDIE legacy */
        'scan-beam':  'scan-beam 2.2s linear infinite',
        'discovery':  'discovery-in 0.3s ease both',
        'fade-in-up': 'fadeInUp 0.5s ease both',
        'fade-in':    'fadeIn 0.4s ease both',
        'spin-slow':  'spin-slow 3s linear infinite',
        'float':      'float 3s ease-in-out infinite',
        'glow':       'glow-em 2s ease-in-out infinite',
        'pulse-ring': 'pulse-ring 2s infinite',
      },
      keyframes: {
        'mesh-drift':  { '0%,100%':{transform:'translate(0,0) scale(1)'}, '33%':{transform:'translate(50px,-35px) scale(1.1)'}, '66%':{transform:'translate(-30px,25px) scale(0.94)'} },
        'rise':        { from:{opacity:'0',transform:'translateY(18px)'}, to:{opacity:'1',transform:'translateY(0)'} },
        'fade-in':     { from:{opacity:'0'}, to:{opacity:'1'} },
        'ping-sm':     { '75%,100%':{transform:'scale(1.8)',opacity:'0'} },
        /* SDIE legacy */
        'fadeInUp':    { from:{opacity:'0',transform:'translateY(16px)'}, to:{opacity:'1',transform:'translateY(0)'} },
        'fadeIn':      { from:{opacity:'0'}, to:{opacity:'1'} },
        'float':       { '0%,100%':{transform:'translateY(0)'}, '50%':{transform:'translateY(-6px)'} },
        'glow-em':     { '0%,100%':{boxShadow:'0 0 8px rgba(16,185,129,0.2)'}, '50%':{boxShadow:'0 0 28px rgba(16,185,129,0.45)'} },
        'pulse-ring':  { '0%':{transform:'scale(0.95)',boxShadow:'0 0 0 0 rgba(16,185,129,0.35)'}, '70%':{transform:'scale(1)',boxShadow:'0 0 0 10px rgba(16,185,129,0)'}, '100%':{transform:'scale(0.95)',boxShadow:'0 0 0 0 rgba(16,185,129,0)'} },
        'scan-beam':   { '0%':{top:'-3px',opacity:'0'}, '5%':{opacity:'1'}, '92%':{opacity:'1'}, '100%':{top:'calc(100% + 3px)',opacity:'0'} },
        'discovery-in':{ from:{opacity:'0',transform:'translateX(-12px)'}, to:{opacity:'1',transform:'translateX(0)'} },
        'spin-slow':   { from:{transform:'rotate(0deg)'}, to:{transform:'rotate(360deg)'} },
        'node-orbit':  { from:{transform:'rotate(0deg) translateX(36px) rotate(0deg)'}, to:{transform:'rotate(360deg) translateX(36px) rotate(-360deg)'} },
        'progress-fill':{ from:{width:'0%'}, to:{width:'var(--progress-width)'} },
      },
    },
  },
  plugins: [],
}
