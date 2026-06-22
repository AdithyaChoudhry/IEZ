import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { LogIn, Droplets, Eye, EyeOff } from 'lucide-react';

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
        {/* Mesh blobs */}
        <div className="absolute inset-0 pointer-events-none overflow-hidden">
          <div className="mesh-blob-a absolute -top-20 -left-20 w-80 h-80 rounded-full blur-3xl" style={{ background: 'rgba(59,130,246,0.08)' }} />
          <div className="mesh-blob-b absolute bottom-0 right-0 w-72 h-72 rounded-full blur-3xl" style={{ background: 'rgba(59,130,246,0.05)' }} />
          <div className="mesh-blob-c absolute top-1/2 left-1/4 w-56 h-56 rounded-full blur-3xl" style={{ background: 'rgba(96,165,250,0.04)' }} />
        </div>

        {/* Logo */}
        <div className="relative">
          <div className="flex items-center gap-3">
            <div
              className="w-10 h-10 rounded-xl flex items-center justify-center"
              style={{ background: 'linear-gradient(135deg, var(--em), #1d4ed8)', boxShadow: '0 0 20px var(--em-glow)' }}
            >
              <Droplets className="w-5 h-5 text-white" />
            </div>
            <div>
              <span
                className="text-xl font-black"
                style={{ fontFamily: "'Space Grotesk', sans-serif", color: 'var(--t0)', letterSpacing: '-0.02em' }}
              >
                i<span className="text-gradient">EZ</span>
              </span>
              <p className="text-[10px] tracking-widest uppercase" style={{ color: 'var(--t2)' }}>
                Intelligent automation of Instrumentation documentation
              </p>
            </div>
          </div>
        </div>

        {/* Centre content */}
        <div className="relative flex-1 flex flex-col justify-center py-8">
          <div
            className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full mb-10 w-fit text-xs font-medium"
            style={{ background: 'var(--em-dim)', border: '1px solid rgba(59,130,246,0.18)', color: 'var(--em-lt)' }}
          >
            <span className="w-1.5 h-1.5 rounded-full bg-blue-400" />
            Developed for VA TECH WABAG
          </div>

          {/* decorative water rings */}
          <div className="relative w-48 h-48 mx-auto">
            <div className="absolute inset-0 rounded-full border border-blue-500/10 animate-ping" style={{ animationDuration: '3s' }} />
            <div className="absolute inset-4 rounded-full border border-blue-500/15 animate-ping" style={{ animationDuration: '3.6s', animationDelay: '0.6s' }} />
            <div className="absolute inset-8 rounded-full border border-blue-400/20 animate-ping" style={{ animationDuration: '4.2s', animationDelay: '1.2s' }} />
            <div
              className="absolute inset-16 rounded-full flex items-center justify-center"
              style={{ background: 'radial-gradient(circle, rgba(59,130,246,0.18) 0%, transparent 70%)' }}
            >
              <Droplets className="w-10 h-10" style={{ color: 'rgba(96,165,250,0.6)' }} />
            </div>
          </div>
        </div>

        <div className="relative">
          <p className="text-[11px]" style={{ color: 'var(--t2)' }}>Built by Akash Balaji · iEZ v3.1</p>
        </div>
      </div>

      {/* ── Right: Form ── */}
      <div className="flex-1 flex items-center justify-center px-6">
        <div className="w-full max-w-sm animate-rise">

          {/* Mobile logo */}
          <div className="lg:hidden flex items-center gap-3 justify-center mb-10">
            <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ background: 'linear-gradient(135deg, var(--em), #1d4ed8)' }}>
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
            <div
              className="mb-6 px-4 py-3 rounded-xl text-sm animate-rise"
              style={{ background: 'rgba(248,113,113,0.08)', border: '1px solid rgba(248,113,113,0.2)', color: 'var(--rose)' }}
            >
              {error}
            </div>
          )}

          <form onSubmit={submit} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold mb-2 uppercase tracking-wider" style={{ color: 'var(--t2)' }}>Username</label>
              <input
                type="text" required autoComplete="username"
                value={username} onChange={e => setUsername(e.target.value)}
                placeholder="your username" className="input-field"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold mb-2 uppercase tracking-wider" style={{ color: 'var(--t2)' }}>Password</label>
              <div className="relative">
                <input
                  type={showPw ? 'text' : 'password'} required autoComplete="current-password"
                  value={password} onChange={e => setPassword(e.target.value)}
                  placeholder="••••••••" className="input-field" style={{ paddingRight: '40px' }}
                />
                <button
                  type="button" tabIndex={-1} onClick={() => setShowPw(!showPw)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 opacity-40 hover:opacity-80 transition-opacity"
                  style={{ color: 'var(--t1)' }}
                >
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
