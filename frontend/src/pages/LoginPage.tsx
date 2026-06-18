import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { LogIn, Droplets, Eye, EyeOff, Waves, Zap, Shield, BarChart3 } from 'lucide-react';

const features = [
  { icon: Zap,       text: 'AI-powered spec extraction from tender PDFs' },
  { icon: BarChart3, text: 'Auto-generate datasheets, I/O lists, cable schedules' },
  { icon: Shield,    text: 'IODB validation with custom engineering rules' },
  { icon: Waves,     text: 'Built for WABAG water treatment projects' },
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
    <div
      className="min-h-screen flex"
      style={{ background: 'var(--bg-base)' }}
    >
      {/* ── Left panel: Branding ── */}
      <div
        className="hidden lg:flex flex-col justify-between w-[45%] p-12 relative overflow-hidden"
        style={{
          background: 'linear-gradient(160deg, #061428 0%, #020d1a 60%, #020d1a 100%)',
          borderRight: '1px solid rgba(14,165,233,0.12)',
        }}
      >
        {/* Background decorations */}
        <div className="absolute inset-0 dot-grid opacity-30 pointer-events-none" />
        <div
          className="absolute top-1/4 left-1/2 -translate-x-1/2 w-96 h-96 rounded-full blur-3xl pointer-events-none"
          style={{ background: 'radial-gradient(circle, rgba(14,165,233,0.08) 0%, transparent 70%)' }}
        />
        <div
          className="absolute bottom-0 left-0 w-80 h-80 rounded-full blur-3xl pointer-events-none"
          style={{ background: 'radial-gradient(circle, rgba(6,182,212,0.06) 0%, transparent 70%)' }}
        />

        {/* Logo */}
        <div className="relative">
          <div className="flex items-center gap-3 mb-3">
            <div
              className="w-11 h-11 rounded-2xl flex items-center justify-center shadow-xl"
              style={{
                background: 'linear-gradient(135deg, #0ea5e9, #0369a1)',
                boxShadow: '0 0 24px rgba(14,165,233,0.3)',
              }}
            >
              <Droplets className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1
                className="text-2xl font-black leading-none"
                style={{ fontFamily: "'Space Grotesk', sans-serif" }}
              >
                <span className="text-white">i</span>
                <span className="text-gradient">EZ</span>
              </h1>
              <p className="text-[10px] tracking-wider uppercase" style={{ color: 'rgba(125,211,252,0.4)' }}>
                Intelligent Engineering Zone
              </p>
            </div>
          </div>
        </div>

        {/* Hero */}
        <div className="relative flex-1 flex flex-col justify-center">
          <div className="mb-8">
            <div
              className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full mb-6 text-xs font-medium"
              style={{
                background: 'rgba(14,165,233,0.1)',
                border: '1px solid rgba(14,165,233,0.2)',
                color: '#38bdf8',
              }}
            >
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              Water Treatment · India
            </div>
            <h2
              className="text-4xl font-black leading-tight mb-4"
              style={{ fontFamily: "'Space Grotesk', sans-serif" }}
            >
              <span className="text-white">Engineering</span>
              <br />
              <span className="text-gradient">Automation</span>
              <br />
              <span className="text-white">Redefined</span>
            </h2>
            <p className="text-base leading-relaxed" style={{ color: 'rgba(147,197,253,0.65)' }}>
              Purpose-built for WABAG instrumentation teams — from IODB validation to AI-powered datasheet generation.
            </p>
          </div>

          {/* Feature list */}
          <div className="space-y-3">
            {features.map((f, i) => {
              const Icon = f.icon;
              return (
                <div
                  key={i}
                  className="flex items-center gap-3 animate-slide-up"
                  style={{ animationDelay: `${i * 100 + 200}ms` }}
                >
                  <div
                    className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0"
                    style={{ background: 'rgba(14,165,233,0.12)', border: '1px solid rgba(14,165,233,0.2)' }}
                  >
                    <Icon className="w-3.5 h-3.5 text-sky-400" />
                  </div>
                  <span className="text-sm" style={{ color: 'rgba(147,197,253,0.7)' }}>{f.text}</span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Bottom credit */}
        <div className="relative">
          <p className="text-[11px]" style={{ color: 'rgba(125,211,252,0.3)' }}>
            Built by Akash B · iEZ v2.0
          </p>
        </div>
      </div>

      {/* ── Right panel: Form ── */}
      <div className="flex-1 flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-sm animate-slide-up">

          {/* Mobile logo */}
          <div className="lg:hidden flex items-center gap-3 justify-center mb-10">
            <div
              className="w-10 h-10 rounded-xl flex items-center justify-center"
              style={{ background: 'linear-gradient(135deg, #0ea5e9, #0369a1)', boxShadow: '0 0 20px rgba(14,165,233,0.3)' }}
            >
              <Droplets className="w-5 h-5 text-white" />
            </div>
            <h1 className="text-2xl font-black" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
              <span className="text-white">i</span><span className="text-gradient">EZ</span>
            </h1>
          </div>

          {/* Card */}
          <div
            className="rounded-2xl p-8"
            style={{
              background: 'rgba(6,20,40,0.85)',
              backdropFilter: 'blur(20px)',
              border: '1px solid rgba(14,165,233,0.18)',
              boxShadow: '0 32px 64px rgba(2,13,26,0.5)',
            }}
          >
            <div className="mb-8">
              <h2
                className="text-2xl font-bold text-white mb-1"
                style={{ fontFamily: "'Space Grotesk', sans-serif" }}
              >
                Sign In
              </h2>
              <p className="text-sm" style={{ color: 'rgba(147,197,253,0.55)' }}>
                Access your instrumentation workspace
              </p>
            </div>

            {error && (
              <div
                className="mb-5 px-4 py-3 rounded-xl text-sm flex items-center gap-2 animate-slide-up"
                style={{
                  background: 'rgba(244,63,94,0.1)',
                  border: '1px solid rgba(244,63,94,0.25)',
                  color: '#fb7185',
                }}
              >
                {error}
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-5">
              <div>
                <label className="block text-xs font-semibold mb-2 tracking-wide uppercase" style={{ color: 'rgba(125,211,252,0.6)' }}>
                  Username
                </label>
                <input
                  type="text"
                  required
                  autoComplete="username"
                  value={username}
                  onChange={e => setUsername(e.target.value)}
                  placeholder="Enter your username"
                  className="w-full px-4 py-3 rounded-xl text-sm outline-none transition-all duration-200"
                  style={{
                    background: 'rgba(2,10,24,0.8)',
                    border: '1px solid rgba(14,165,233,0.2)',
                    color: '#f0f9ff',
                  }}
                  onFocus={e => (e.currentTarget.style.borderColor = 'rgba(14,165,233,0.55)')}
                  onBlur={e => (e.currentTarget.style.borderColor = 'rgba(14,165,233,0.2)')}
                />
              </div>

              <div>
                <label className="block text-xs font-semibold mb-2 tracking-wide uppercase" style={{ color: 'rgba(125,211,252,0.6)' }}>
                  Password
                </label>
                <div className="relative">
                  <input
                    type={showPw ? 'text' : 'password'}
                    required
                    autoComplete="current-password"
                    value={password}
                    onChange={e => setPassword(e.target.value)}
                    placeholder="Enter your password"
                    className="w-full px-4 py-3 pr-11 rounded-xl text-sm outline-none transition-all duration-200"
                    style={{
                      background: 'rgba(2,10,24,0.8)',
                      border: '1px solid rgba(14,165,233,0.2)',
                      color: '#f0f9ff',
                    }}
                    onFocus={e => (e.currentTarget.style.borderColor = 'rgba(14,165,233,0.55)')}
                    onBlur={e => (e.currentTarget.style.borderColor = 'rgba(14,165,233,0.2)')}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPw(!showPw)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 transition-colors"
                    style={{ color: 'rgba(125,211,252,0.4)' }}
                    tabIndex={-1}
                  >
                    {showPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full py-3 px-4 rounded-xl font-bold text-sm flex items-center justify-center gap-2 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed mt-2"
                style={{
                  background: loading ? 'rgba(14,165,233,0.4)' : 'linear-gradient(135deg, #0ea5e9, #0369a1)',
                  color: 'white',
                  boxShadow: loading ? 'none' : '0 8px 24px rgba(14,165,233,0.25)',
                }}
              >
                {loading ? (
                  <span className="flex items-center gap-2">
                    <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    Signing in…
                  </span>
                ) : (
                  <>
                    <LogIn className="w-4 h-4" />
                    Sign In
                  </>
                )}
              </button>
            </form>

            <div className="mt-6 text-center text-sm" style={{ color: 'rgba(125,211,252,0.45)' }}>
              Don't have an account?{' '}
              <Link
                to="/register"
                className="font-semibold transition-colors"
                style={{ color: '#38bdf8' }}
                onMouseEnter={e => (e.currentTarget.style.color = '#7dd3fc')}
                onMouseLeave={e => (e.currentTarget.style.color = '#38bdf8')}
              >
                Sign up
              </Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
