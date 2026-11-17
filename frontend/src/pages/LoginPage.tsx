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
    <div className="min-h-screen relative overflow-hidden flex items-center justify-center px-5 py-12" style={{ background: 'var(--s0)' }}>
      {/* ambient light */}
      <div className="ambient" aria-hidden><i /><i /><i /></div>

      <div className="relative w-full max-w-[400px] animate-rise">
        <div className="flex flex-col items-center text-center mb-9">
          <div className="w-[76px] h-[76px] rounded-[24px] flex items-center justify-center mb-7 animate-float"
            style={{ background: 'var(--grad)', boxShadow: '0 18px 40px -12px var(--em-glow)' }}>
            <Droplets className="w-9 h-9 text-white" />
          </div>
          <h1 className="font-bold" style={{ fontFamily: 'var(--font-display)', color: 'var(--t0)', fontSize: 34, letterSpacing: '-0.04em', lineHeight: 1.08 }}>
            Sign in to i<span className="text-grad">EZ</span>.
          </h1>
          <p className="mt-2 text-[15px]" style={{ color: 'var(--t1)' }}>Instrumentation Engineering EZ · VA TECH WABAG</p>
        </div>

        {error && (
          <div className="mb-5 px-4 py-3 rounded-2xl text-sm pop-in"
            style={{ background: 'color-mix(in srgb, var(--bad) 9%, transparent)', border: '1px solid color-mix(in srgb, var(--bad) 26%, transparent)', color: 'var(--bad)' }}>
            {error}
          </div>
        )}

        <form onSubmit={submit} className="glass-panel p-7 space-y-4" style={{ borderRadius: 28 }}>
          <div>
            <label className="block text-[13px] font-medium mb-1.5" style={{ color: 'var(--t1)' }}>Username</label>
            <input type="text" required autoComplete="username" value={username} onChange={e => setUsername(e.target.value)}
              placeholder="Your username" className="input-field" />
          </div>
          <div>
            <label className="block text-[13px] font-medium mb-1.5" style={{ color: 'var(--t1)' }}>Password</label>
            <div className="relative">
              <input type={showPw ? 'text' : 'password'} required autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)}
                placeholder="Password" className="input-field" style={{ paddingRight: '44px' }} />
              <button type="button" tabIndex={-1} onClick={() => setShowPw(!showPw)}
                className="absolute right-3 top-1/2 -translate-y-1/2 opacity-50 hover:opacity-90 transition-opacity" style={{ color: 'var(--t1)' }}>
                {showPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>
          <button type="submit" disabled={loading} className="btn btn-primary w-full py-3 mt-2 text-[15px]">
            {loading
              ? <><span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />Signing in…</>
              : <><LogIn className="w-4 h-4" />Sign In</>}
          </button>
        </form>

        <p className="mt-6 text-center text-[14px]" style={{ color: 'var(--t1)' }}>
          Don't have an account?{' '}
          <Link to="/register" className="font-medium" style={{ color: 'var(--em-lt)' }}>Sign up</Link>
        </p>
        <p className="text-center text-[11px] mt-8" style={{ color: 'var(--t2)' }}>Built by Akash Balaji · iEZ v3.1</p>
      </div>
    </div>
  );
}
