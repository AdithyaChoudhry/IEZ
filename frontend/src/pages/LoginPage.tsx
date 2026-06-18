import React, { useState, useEffect, useRef } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { LogIn, Droplets, Eye, EyeOff, Zap, Shield, BarChart3, Waves } from 'lucide-react';

/* ── Rising particle canvas ─────────────────────────────────────────────── */
function ParticleCanvas() {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    const resize = () => { canvas.width = canvas.offsetWidth; canvas.height = canvas.offsetHeight; };
    resize();
    window.addEventListener('resize', resize);

    type P = { x: number; y: number; r: number; vy: number; vx: number; o: number; color: string };
    const colors = ['rgba(16,185,129,', 'rgba(52,211,153,', 'rgba(245,158,11,'];
    const pts: P[] = Array.from({ length: 35 }, () => ({
      x: Math.random() * (canvas.width || 600),
      y: Math.random() * (canvas.height || 800),
      r: Math.random() * 2 + 0.5,
      vy: -(Math.random() * 0.35 + 0.08),
      vx: (Math.random() - 0.5) * 0.12,
      o: Math.random() * 0.35 + 0.08,
      color: colors[Math.floor(Math.random() * colors.length)],
    }));

    let raf: number;
    function draw() {
      ctx!.clearRect(0, 0, canvas!.width, canvas!.height);
      pts.forEach(p => {
        ctx!.beginPath();
        ctx!.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx!.fillStyle = p.color + p.o + ')';
        ctx!.fill();
        p.y += p.vy; p.x += p.vx; p.o -= 0.0006;
        if (p.y < -5 || p.o <= 0) {
          p.x = Math.random() * canvas!.width;
          p.y = canvas!.height + 5;
          p.o = Math.random() * 0.35 + 0.08;
          p.r = Math.random() * 2 + 0.5;
        }
      });
      raf = requestAnimationFrame(draw);
    }
    draw();
    return () => { cancelAnimationFrame(raf); window.removeEventListener('resize', resize); };
  }, []);
  return <canvas ref={ref} className="absolute inset-0 w-full h-full pointer-events-none" />;
}

const features = [
  { icon: Zap,       label: 'AI spec extraction from tender PDFs' },
  { icon: BarChart3, label: 'Auto-generate datasheets & I/O lists' },
  { icon: Shield,    label: 'IODB validation with custom rules' },
  { icon: Waves,     label: 'Built for WABAG water treatment' },
];

export default function LoginPage() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setError(''); setLoading(true);
    try { await login({ username, password }); navigate('/'); }
    catch (err: any) { setError(err.response?.data?.detail || 'Login failed. Please try again.'); }
    finally { setLoading(false); }
  };

  return (
    <div className="min-h-screen flex" style={{ background: 'var(--s0)' }}>

      {/* ── Left: Branding ── */}
      <div
        className="hidden lg:flex flex-col justify-between w-[46%] relative overflow-hidden p-12"
        style={{ background: 'var(--s1)', borderRight: '1px solid var(--b1)' }}
      >
        <ParticleCanvas />
        {/* Mesh blobs */}
        <div className="absolute inset-0 pointer-events-none overflow-hidden">
          <div className="mesh-blob-a absolute -top-20 -left-20 w-80 h-80 rounded-full blur-3xl" style={{ background: 'rgba(16,185,129,0.06)' }} />
          <div className="mesh-blob-b absolute bottom-0 right-0 w-72 h-72 rounded-full blur-3xl" style={{ background: 'rgba(245,158,11,0.04)' }} />
        </div>

        {/* Logo */}
        <div className="relative">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ background: 'linear-gradient(135deg, var(--em), #059669)', boxShadow: '0 0 20px var(--em-glow)' }}>
              <Droplets className="w-5 h-5 text-white" />
            </div>
            <div>
              <span className="text-xl font-black" style={{ fontFamily: "'Space Grotesk', sans-serif", color: 'var(--t0)', letterSpacing: '-0.02em' }}>
                i<span className="text-gradient">EZ</span>
              </span>
              <p className="text-[10px] tracking-widest uppercase" style={{ color: 'var(--t2)' }}>Intelligent Engineering Zone</p>
            </div>
          </div>
        </div>

        {/* Hero text */}
        <div className="relative flex-1 flex flex-col justify-center py-8">
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full mb-8 w-fit text-xs font-medium"
            style={{ background: 'var(--em-dim)', border: '1px solid rgba(16,185,129,0.18)', color: 'var(--em-lt)' }}>
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
            WABAG Water Treatment · India
          </div>

          <h2
            className="text-4xl font-black mb-5 leading-tight"
            style={{ fontFamily: "'Space Grotesk', sans-serif", color: 'var(--t0)', letterSpacing: '-0.025em' }}
          >
            Engineering<br />
            <span className="text-gradient">automation</span><br />
            redefined.
          </h2>
          <p className="text-sm mb-10" style={{ color: 'var(--t1)', lineHeight: '1.75' }}>
            Purpose-built for WABAG instrumentation teams — from IODB validation to AI-powered datasheet generation.
          </p>

          <div className="space-y-3">
            {features.map((f, i) => {
              const Icon = f.icon;
              return (
                <div key={i} className="flex items-center gap-3 animate-rise" style={{ animationDelay: `${i * 80 + 200}ms` }}>
                  <div className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0" style={{ background: 'var(--s2)', border: '1px solid var(--b1)' }}>
                    <Icon className="w-3.5 h-3.5" style={{ color: 'var(--em)' }} />
                  </div>
                  <span className="text-sm" style={{ color: 'var(--t1)' }}>{f.label}</span>
                </div>
              );
            })}
          </div>
        </div>

        <div className="relative">
          <p className="text-[11px]" style={{ color: 'var(--t2)' }}>Built by Akash B · iEZ v2.0</p>
        </div>
      </div>

      {/* ── Right: Form ── */}
      <div className="flex-1 flex items-center justify-center px-6">
        <div className="w-full max-w-sm animate-rise">

          {/* Mobile logo */}
          <div className="lg:hidden flex items-center gap-3 justify-center mb-10">
            <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ background: 'linear-gradient(135deg, var(--em), #059669)' }}>
              <Droplets className="w-5 h-5 text-white" />
            </div>
            <span className="text-2xl font-black" style={{ fontFamily: "'Space Grotesk', sans-serif", color: 'var(--t0)' }}>
              i<span className="text-gradient">EZ</span>
            </span>
          </div>

          <div className="mb-8">
            <h2 className="text-2xl font-bold mb-1" style={{ fontFamily: "'Space Grotesk', sans-serif", color: 'var(--t0)' }}>Sign in</h2>
            <p className="text-sm" style={{ color: 'var(--t1)' }}>Enter your credentials to continue</p>
          </div>

          {error && (
            <div className="mb-6 px-4 py-3 rounded-xl text-sm animate-rise"
              style={{ background: 'rgba(248,113,113,0.08)', border: '1px solid rgba(248,113,113,0.2)', color: 'var(--rose)' }}>
              {error}
            </div>
          )}

          <form onSubmit={submit} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold mb-2 uppercase tracking-wider" style={{ color: 'var(--t2)' }}>Username</label>
              <input type="text" required autoComplete="username" value={username} onChange={e => setUsername(e.target.value)} placeholder="your username" className="input-field" />
            </div>
            <div>
              <label className="block text-xs font-semibold mb-2 uppercase tracking-wider" style={{ color: 'var(--t2)' }}>Password</label>
              <div className="relative">
                <input
                  type={showPw ? 'text' : 'password'} required autoComplete="current-password"
                  value={password} onChange={e => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="input-field"
                  style={{ paddingRight: '40px' }}
                />
                <button type="button" tabIndex={-1} onClick={() => setShowPw(!showPw)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 opacity-40 hover:opacity-80 transition-opacity"
                  style={{ color: 'var(--t1)' }}>
                  {showPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>
            <button type="submit" disabled={loading} className="btn btn-primary w-full py-3 mt-2 text-sm">
              {loading
                ? <><span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />Signing in…</>
                : <><LogIn className="w-4 h-4" />Sign In</>}
            </button>
          </form>

          <p className="mt-6 text-center text-sm" style={{ color: 'var(--t1)' }}>
            Don't have an account?{' '}
            <Link to="/register" className="font-semibold" style={{ color: 'var(--em-lt)' }}>Sign up</Link>
          </p>
        </div>
      </div>
    </div>
  );
}
