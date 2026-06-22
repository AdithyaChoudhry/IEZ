import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { UserPlus, Droplets, Eye, EyeOff } from 'lucide-react';

export default function RegisterPage() {
  const [email, setEmail]         = useState('');
  const [username, setUsername]   = useState('');
  const [password, setPassword]   = useState('');
  const [confirm, setConfirm]     = useState('');
  const [showPw, setShowPw]       = useState(false);
  const [error, setError]         = useState('');
  const [loading, setLoading]     = useState(false);
  const { register } = useAuth();
  const navigate = useNavigate();

  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setError('');
    if (password !== confirm)    { setError('Passwords do not match'); return; }
    if (password.length < 8)     { setError('Password must be at least 8 characters'); return; }
    setLoading(true);
    try { await register({ email, username, password }); navigate('/'); }
    catch (err: any) { setError(err.response?.data?.detail || 'Registration failed.'); }
    finally { setLoading(false); }
  };

  return (
    <div className="min-h-screen flex items-center justify-center px-4 py-12" style={{ background: 'var(--s0)' }}>
      <div className="fixed inset-0 pointer-events-none overflow-hidden">
        <div className="mesh-blob-a absolute top-1/3 left-1/2 -translate-x-1/2 w-96 h-96 rounded-full blur-3xl" style={{ background: 'rgba(16,185,129,0.04)' }} />
      </div>

      <div className="relative w-full max-w-md animate-rise">
        {/* Logo */}
        <div className="flex items-center gap-3 justify-center mb-10">
          <div className="w-9 h-9 rounded-xl flex items-center justify-center" style={{ background: 'linear-gradient(135deg, var(--em), #059669)', boxShadow: '0 0 16px var(--em-glow)' }}>
            <Droplets className="w-4 h-4 text-white" />
          </div>
          <span className="text-xl font-black" style={{ fontFamily: "'Space Grotesk', sans-serif", color: 'var(--t0)' }}>
            i<span className="text-gradient">EZ</span>
          </span>
        </div>

        {/* Card */}
        <div className="rounded-2xl p-8" style={{ background: 'var(--s2)', border: '1px solid var(--b1)', boxShadow: '0 24px 64px rgba(0,0,0,0.4)' }}>
          <div className="mb-7">
            <h2 className="text-2xl font-bold mb-1" style={{ fontFamily: "'Space Grotesk', sans-serif", color: 'var(--t0)' }}>Create account</h2>
            <p className="text-sm" style={{ color: 'var(--t1)' }}>Join the iEZ engineering platform</p>
          </div>

          {error && (
            <div className="mb-5 px-4 py-3 rounded-xl text-sm" style={{ background: 'rgba(248,113,113,0.08)', border: '1px solid rgba(248,113,113,0.2)', color: 'var(--rose)' }}>
              {error}
            </div>
          )}

          <form onSubmit={submit} className="space-y-4">
            {[
              { label: 'Email',    type: 'email', val: email,    set: setEmail,    ac: 'email',    ph: 'your.email@company.com' },
              { label: 'Username', type: 'text',  val: username, set: setUsername, ac: 'username', ph: 'choose a username' },
            ].map(f => (
              <div key={f.label}>
                <label className="block text-xs font-semibold mb-1.5 uppercase tracking-wider" style={{ color: 'var(--t2)' }}>{f.label}</label>
                <input type={f.type} required autoComplete={f.ac} value={f.val} onChange={e => f.set(e.target.value)} placeholder={f.ph} className="input-field" />
              </div>
            ))}

            <div>
              <label className="block text-xs font-semibold mb-1.5 uppercase tracking-wider" style={{ color: 'var(--t2)' }}>Password</label>
              <div className="relative">
                <input type={showPw ? 'text' : 'password'} required minLength={8} autoComplete="new-password" value={password} onChange={e => setPassword(e.target.value)} placeholder="at least 8 characters" className="input-field" style={{ paddingRight: '40px' }} />
                <button type="button" tabIndex={-1} onClick={() => setShowPw(!showPw)} className="absolute right-3 top-1/2 -translate-y-1/2 opacity-40 hover:opacity-80 transition-opacity" style={{ color: 'var(--t1)' }}>
                  {showPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold mb-1.5 uppercase tracking-wider" style={{ color: 'var(--t2)' }}>Confirm Password</label>
              <input type="password" required autoComplete="new-password" value={confirm} onChange={e => setConfirm(e.target.value)} placeholder="re-enter password" className="input-field" />
            </div>

            <button type="submit" disabled={loading} className="btn btn-primary w-full py-3 text-sm mt-1">
              {loading
                ? <><span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />Creating…</>
                : <><UserPlus className="w-4 h-4" />Create Account</>}
            </button>
          </form>

          <p className="mt-6 text-center text-sm" style={{ color: 'var(--t1)' }}>
            Already have an account?{' '}
            <Link to="/login" className="font-semibold" style={{ color: 'var(--em-lt)' }}>Sign in</Link>
          </p>
        </div>

        <p className="text-center text-[11px] mt-5" style={{ color: 'var(--t2)' }}>
          Built by Akash Balaji · iEZ v3.1 · Developed for VA TECH WABAG
        </p>
      </div>
    </div>
  );
}
