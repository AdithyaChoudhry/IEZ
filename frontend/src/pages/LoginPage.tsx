import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { LogIn, Eye, EyeOff } from 'lucide-react';
import { Brand, BrandMark } from '@/components/layout/TopNav';

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
    <div className="min-h-screen grid lg:grid-cols-[1.1fr_1fr]" style={{ background: 'var(--s0)' }}>
      {/* ── Statement panel (always ink) ── */}
      <div className="hidden lg:flex relative flex-col justify-between p-12 overflow-hidden" style={{ background: '#171614', color: '#f6f5f2' }}>
        <div className="absolute inset-0 pointer-events-none" style={{ backgroundImage: 'linear-gradient(rgba(255,248,235,.06) 1px, transparent 1px), linear-gradient(90deg, rgba(255,248,235,.06) 1px, transparent 1px)', backgroundSize: '40px 40px' }} />
        <div className="relative flex items-center gap-2.5">
          <BrandMark ink="#f6f5f2" fg="#171614" />
          <span className="text-[17px] font-bold" style={{ fontFamily: 'var(--font-display)', letterSpacing: '-0.035em' }}>iEZ</span>
        </div>
        <div className="relative">
          <p className="mono text-[11px] tracking-[.12em]" style={{ color: '#a8a49b' }}><span style={{ color: '#ff6a2b' }}>●</span>&nbsp; INSTRUMENTATION ENGINEERING EZ</p>
          <h1 className="mt-6 font-semibold" style={{ fontFamily: 'var(--font-display)', fontSize: 'clamp(44px, 4.6vw, 68px)', lineHeight: 1.0, letterSpacing: '-0.045em' }}>
            From one IODB<br />to issued drawings<span style={{ color: '#ff6a2b' }}>.</span>
          </h1>
          <div className="relative mt-12 h-px max-w-md" style={{ background: 'rgba(255,248,235,.25)' }}>
            <span className="absolute -top-[3px] w-[7px] h-[7px] rounded-full" style={{ background: '#ff6a2b', boxShadow: '0 0 0 4px rgba(255,106,43,.18)', animation: 'travel 5s cubic-bezier(.45,0,.55,1) infinite' }} />
          </div>
          <div className="mt-4 flex justify-between max-w-md mono text-[10.5px]" style={{ color: '#a8a49b' }}>
            <span>IODB</span><span>VALIDATE</span><span>LISTS</span><span>CABLES</span><span>LOOPS</span><span>ISSUE</span>
          </div>
        </div>
        <p className="relative mono text-[11px]" style={{ color: '#6f6b64' }}>VA TECH WABAG · BUILT BY AKASH BALAJI · V3.1</p>
      </div>

      {/* ── Form ── */}
      <div className="flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-[380px] page-enter">
          <div className="lg:hidden mb-10"><Brand /></div>
          <p className="eyebrow">Sign in</p>
          <h2 className="mt-3 font-semibold" style={{ fontFamily: 'var(--font-display)', color: 'var(--t0)', fontSize: 34, letterSpacing: '-0.04em', lineHeight: 1.1 }}>Welcome back<span className="signal">.</span></h2>
          <p className="mt-2 text-[15px]" style={{ color: 'var(--t1)' }}>Use your iEZ account to continue.</p>

          {error && (
            <div className="mt-6 px-4 py-3 rounded-[10px] text-sm pop-in"
              style={{ background: 'color-mix(in srgb, var(--bad) 8%, transparent)', border: '1px solid color-mix(in srgb, var(--bad) 28%, transparent)', color: 'var(--bad)' }}>
              {error}
            </div>
          )}

          <form onSubmit={submit} className="mt-8 space-y-4">
            <div>
              <label className="block text-[13px] font-medium mb-1.5" style={{ color: 'var(--t0)' }}>Username</label>
              <input type="text" required autoComplete="username" value={username} onChange={e => setUsername(e.target.value)} placeholder="Your username" className="input-field" />
            </div>
            <div>
              <label className="block text-[13px] font-medium mb-1.5" style={{ color: 'var(--t0)' }}>Password</label>
              <div className="relative">
                <input type={showPw ? 'text' : 'password'} required autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)}
                  placeholder="Password" className="input-field" style={{ paddingRight: '44px' }} />
                <button type="button" tabIndex={-1} onClick={() => setShowPw(!showPw)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 opacity-50 hover:opacity-90 transition-opacity" style={{ color: 'var(--t1)' }}>
                  {showPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>
            <button type="submit" disabled={loading} className="btn btn-primary w-full h-12 mt-2 text-[15px]">
              {loading
                ? <><span className="w-4 h-4 border-2 border-current/30 border-t-current rounded-full animate-spin" />Signing in…</>
                : <><LogIn className="w-4 h-4" />Sign in</>}
            </button>
          </form>

          <p className="mt-6 text-[14px]" style={{ color: 'var(--t1)' }}>
            New to iEZ?{' '}
            <Link to="/register" className="font-medium underline underline-offset-4" style={{ color: 'var(--t0)' }}>Create an account</Link>
          </p>
        </div>
      </div>
    </div>
  );
}
