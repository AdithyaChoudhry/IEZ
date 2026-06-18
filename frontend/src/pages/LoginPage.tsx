import React, { useState, useEffect, useRef } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { LogIn, Droplets, Eye, EyeOff, Zap, Shield, BarChart3, Waves } from 'lucide-react';

/* ── Canvas particle system (water bubbles) ──────────────────────────────── */
function WaterCanvas() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    function resize() {
      canvas!.width = canvas!.offsetWidth;
      canvas!.height = canvas!.offsetHeight;
    }
    resize();
    window.addEventListener('resize', resize);

    type Particle = { x:number; y:number; r:number; vy:number; vx:number; opacity:number; color:string; };
    const colors = ['rgba(20,184,166,', 'rgba(167,139,250,', 'rgba(96,165,250,'];
    const particles: Particle[] = Array.from({ length: 40 }, () => ({
      x: Math.random() * canvas!.width,
      y: Math.random() * canvas!.height,
      r: Math.random() * 2.5 + 0.5,
      vy: -(Math.random() * 0.4 + 0.1),
      vx: (Math.random() - 0.5) * 0.15,
      opacity: Math.random() * 0.4 + 0.1,
      color: colors[Math.floor(Math.random() * colors.length)],
    }));

    let rafId: number;
    function draw() {
      ctx!.clearRect(0, 0, canvas!.width, canvas!.height);
      particles.forEach(p => {
        ctx!.beginPath();
        ctx!.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx!.fillStyle = p.color + p.opacity + ')';
        ctx!.fill();

        p.y += p.vy;
        p.x += p.vx;
        p.opacity -= 0.0008;

        if (p.y < -5 || p.opacity <= 0) {
          p.x = Math.random() * canvas!.width;
          p.y = canvas!.height + 5;
          p.opacity = Math.random() * 0.4 + 0.1;
          p.r = Math.random() * 2.5 + 0.5;
        }
      });
      rafId = requestAnimationFrame(draw);
    }
    draw();

    return () => { cancelAnimationFrame(rafId); window.removeEventListener('resize', resize); };
  }, []);

  return <canvas ref={canvasRef} className="absolute inset-0 w-full h-full pointer-events-none" />;
}

const features = [
  { icon: Zap,      label: 'AI spec extraction from tender PDFs' },
  { icon: BarChart3,label: 'Auto-generate datasheets & I/O lists' },
  { icon: Shield,   label: 'IODB validation with custom rules' },
  { icon: Waves,    label: 'Built for WABAG water treatment' },
];

export default function LoginPage() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await login({ username, password });
      navigate('/');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Login failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex" style={{ background:'var(--s0)' }}>

      {/* ── Left — Branding ── */}
      <div
        className="hidden lg:flex flex-col justify-between w-[46%] relative overflow-hidden p-12"
        style={{ background:'var(--s1)', borderRight:'1px solid var(--b1)' }}
      >
        <WaterCanvas />

        {/* Mesh blobs */}
        <div className="absolute inset-0 pointer-events-none overflow-hidden">
          <div className="mesh-blob-1 absolute -top-24 -left-24 w-80 h-80 rounded-full blur-3xl" style={{ background:'rgba(20,184,166,0.07)' }} />
          <div className="mesh-blob-2 absolute bottom-0 right-0 w-72 h-72 rounded-full blur-3xl" style={{ background:'rgba(167,139,250,0.06)' }} />
        </div>

        {/* Content */}
        <div className="relative">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ background:'linear-gradient(135deg,var(--teal),#0d9488)', boxShadow:'0 0 20px rgba(20,184,166,0.2)' }}>
              <Droplets className="w-5 h-5 text-white" />
            </div>
            <div>
              <span className="text-xl font-black" style={{ fontFamily:"'Space Grotesk',sans-serif", color:'var(--t0)', letterSpacing:'-0.02em' }}>
                i<span className="text-gradient">EZ</span>
              </span>
              <p className="text-[10px] tracking-widest uppercase" style={{ color:'var(--t2)' }}>Intelligent Engineering Zone</p>
            </div>
          </div>
        </div>

        <div className="relative flex-1 flex flex-col justify-center py-8">
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full mb-8 w-fit text-xs font-medium"
            style={{ background:'rgba(20,184,166,0.08)', border:'1px solid rgba(20,184,166,0.15)', color:'var(--teal-lt)' }}>
            <span className="w-1.5 h-1.5 rounded-full bg-green-400" />
            WABAG Water Treatment · India
          </div>

          <h2
            className="text-4xl font-black mb-5 leading-tight"
            style={{ fontFamily:"'Space Grotesk',sans-serif", color:'var(--t0)', letterSpacing:'-0.025em' }}
          >
            Engineering<br />
            <span className="text-gradient">automation</span><br />
            redefined.
          </h2>

          <p className="text-sm mb-10" style={{ color:'var(--t1)', lineHeight:'1.75' }}>
            Purpose-built for WABAG instrumentation teams — from IODB validation to AI-powered datasheet generation.
          </p>

          <div className="space-y-3">
            {features.map((f, i) => {
              const Icon = f.icon;
              return (
                <div key={i} className="flex items-center gap-3 animate-rise" style={{ animationDelay:`${i * 80 + 200}ms` }}>
                  <div className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0"
                    style={{ background:'var(--s2)', border:'1px solid var(--b1)' }}>
                    <Icon className="w-3.5 h-3.5" style={{ color:'var(--teal)' }} />
                  </div>
                  <span className="text-sm" style={{ color:'var(--t1)' }}>{f.label}</span>
                </div>
              );
            })}
          </div>
        </div>

        <div className="relative">
          <p className="text-[11px]" style={{ color:'var(--t2)' }}>Built by Akash B · iEZ v2.0</p>
        </div>
      </div>

      {/* ── Right — Form ── */}
      <div className="flex-1 flex items-center justify-center px-6">
        <div className="w-full max-w-sm animate-rise">

          {/* Mobile logo */}
          <div className="lg:hidden flex items-center gap-3 justify-center mb-10">
            <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ background:'linear-gradient(135deg,var(--teal),#0d9488)' }}>
              <Droplets className="w-5 h-5 text-white" />
            </div>
            <span className="text-2xl font-black" style={{ fontFamily:"'Space Grotesk',sans-serif", color:'var(--t0)' }}>
              i<span className="text-gradient">EZ</span>
            </span>
          </div>

          <div className="mb-8">
            <h2 className="text-2xl font-bold mb-1" style={{ fontFamily:"'Space Grotesk',sans-serif", color:'var(--t0)' }}>
              Sign in
            </h2>
            <p className="text-sm" style={{ color:'var(--t1)' }}>Enter your credentials to continue</p>
          </div>

          {error && (
            <div className="mb-6 px-4 py-3 rounded-xl text-sm animate-rise"
              style={{ background:'rgba(248,113,113,0.08)', border:'1px solid rgba(248,113,113,0.2)', color:'var(--rose)' }}>
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold mb-2 uppercase tracking-wider" style={{ color:'var(--t2)' }}>
                Username
              </label>
              <input
                type="text" required autoComplete="username"
                value={username} onChange={e => setUsername(e.target.value)}
                placeholder="your username"
                className="input-field w-full"
                style={{ width:'100%' }}
              />
            </div>

            <div>
              <label className="block text-xs font-semibold mb-2 uppercase tracking-wider" style={{ color:'var(--t2)' }}>
                Password
              </label>
              <div className="relative">
                <input
                  type={showPw ? 'text' : 'password'} required autoComplete="current-password"
                  value={password} onChange={e => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="input-field w-full pr-10"
                  style={{ paddingRight:'40px' }}
                />
                <button
                  type="button" tabIndex={-1} onClick={() => setShowPw(!showPw)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 transition-opacity hover:opacity-100 opacity-50"
                  style={{ color:'var(--t1)' }}
                >
                  {showPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            <button
              type="submit" disabled={loading}
              className="btn btn-primary w-full py-3 mt-2 text-sm"
            >
              {loading ? (
                <>
                  <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  Signing in…
                </>
              ) : (
                <>
                  <LogIn className="w-4 h-4" />
                  Sign In
                </>
              )}
            </button>
          </form>

          <p className="mt-6 text-center text-sm" style={{ color:'var(--t1)' }}>
            Don't have an account?{' '}
            <Link
              to="/register"
              className="font-semibold transition-colors"
              style={{ color:'var(--teal-lt)' }}
            >
              Sign up
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
