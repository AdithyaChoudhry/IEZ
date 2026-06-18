import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { UserPlus, Droplets, Eye, EyeOff } from 'lucide-react';

export default function RegisterPage() {
  const [email, setEmail] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { register } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (password !== confirmPassword) { setError('Passwords do not match'); return; }
    if (password.length < 8) { setError('Password must be at least 8 characters'); return; }
    setLoading(true);
    try {
      await register({ email, username, password });
      navigate('/');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Registration failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const inputStyle = {
    background: 'rgba(2,10,24,0.8)',
    border: '1px solid rgba(14,165,233,0.2)',
    color: '#f0f9ff',
  };
  const onFocus = (e: React.FocusEvent<HTMLInputElement>) =>
    (e.currentTarget.style.borderColor = 'rgba(14,165,233,0.55)');
  const onBlur = (e: React.FocusEvent<HTMLInputElement>) =>
    (e.currentTarget.style.borderColor = 'rgba(14,165,233,0.2)');

  return (
    <div className="min-h-screen flex items-center justify-center px-4 py-12" style={{ background: 'var(--bg-base)' }}>
      {/* Background dots */}
      <div className="fixed inset-0 dot-grid opacity-20 pointer-events-none" />
      <div
        className="fixed top-1/4 left-1/2 -translate-x-1/2 w-[600px] h-[400px] rounded-full blur-3xl pointer-events-none"
        style={{ background: 'radial-gradient(ellipse, rgba(14,165,233,0.07) 0%, transparent 70%)' }}
      />

      <div className="relative w-full max-w-md animate-slide-up">
        {/* Logo */}
        <div className="flex items-center gap-3 justify-center mb-8">
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
            background: 'rgba(6,20,40,0.9)',
            backdropFilter: 'blur(20px)',
            border: '1px solid rgba(14,165,233,0.18)',
            boxShadow: '0 32px 64px rgba(2,13,26,0.5)',
          }}
        >
          <div className="mb-7">
            <h2 className="text-2xl font-bold text-white mb-1" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
              Create Account
            </h2>
            <p className="text-sm" style={{ color: 'rgba(147,197,253,0.5)' }}>
              Join the iEZ engineering platform
            </p>
          </div>

          {error && (
            <div
              className="mb-5 px-4 py-3 rounded-xl text-sm animate-slide-up"
              style={{ background: 'rgba(244,63,94,0.1)', border: '1px solid rgba(244,63,94,0.25)', color: '#fb7185' }}
            >
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Email */}
            <div>
              <label className="block text-xs font-semibold mb-1.5 tracking-wide uppercase" style={{ color: 'rgba(125,211,252,0.6)' }}>
                Email
              </label>
              <input
                type="email" required autoComplete="email"
                value={email} onChange={e => setEmail(e.target.value)}
                placeholder="your.email@example.com"
                className="w-full px-4 py-2.5 rounded-xl text-sm outline-none transition-all duration-200"
                style={inputStyle} onFocus={onFocus} onBlur={onBlur}
              />
            </div>

            {/* Username */}
            <div>
              <label className="block text-xs font-semibold mb-1.5 tracking-wide uppercase" style={{ color: 'rgba(125,211,252,0.6)' }}>
                Username
              </label>
              <input
                type="text" required autoComplete="username" minLength={3} maxLength={50}
                value={username} onChange={e => setUsername(e.target.value)}
                placeholder="Choose a username"
                className="w-full px-4 py-2.5 rounded-xl text-sm outline-none transition-all duration-200"
                style={inputStyle} onFocus={onFocus} onBlur={onBlur}
              />
            </div>

            {/* Password */}
            <div>
              <label className="block text-xs font-semibold mb-1.5 tracking-wide uppercase" style={{ color: 'rgba(125,211,252,0.6)' }}>
                Password
              </label>
              <div className="relative">
                <input
                  type={showPw ? 'text' : 'password'} required autoComplete="new-password" minLength={8}
                  value={password} onChange={e => setPassword(e.target.value)}
                  placeholder="At least 8 characters"
                  className="w-full px-4 py-2.5 pr-10 rounded-xl text-sm outline-none transition-all duration-200"
                  style={inputStyle} onFocus={onFocus} onBlur={onBlur}
                />
                <button type="button" onClick={() => setShowPw(!showPw)} className="absolute right-3 top-1/2 -translate-y-1/2" style={{ color: 'rgba(125,211,252,0.35)' }} tabIndex={-1}>
                  {showPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            {/* Confirm Password */}
            <div>
              <label className="block text-xs font-semibold mb-1.5 tracking-wide uppercase" style={{ color: 'rgba(125,211,252,0.6)' }}>
                Confirm Password
              </label>
              <input
                type="password" required autoComplete="new-password"
                value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)}
                placeholder="Re-enter password"
                className="w-full px-4 py-2.5 rounded-xl text-sm outline-none transition-all duration-200"
                style={inputStyle} onFocus={onFocus} onBlur={onBlur}
              />
            </div>

            <button
              type="submit" disabled={loading}
              className="w-full py-3 px-4 rounded-xl font-bold text-sm flex items-center justify-center gap-2 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed mt-1"
              style={{
                background: loading ? 'rgba(14,165,233,0.4)' : 'linear-gradient(135deg, #0ea5e9, #0369a1)',
                color: 'white',
                boxShadow: loading ? 'none' : '0 8px 24px rgba(14,165,233,0.25)',
              }}
            >
              {loading ? (
                <span className="flex items-center gap-2">
                  <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  Creating account…
                </span>
              ) : (
                <>
                  <UserPlus className="w-4 h-4" />
                  Create Account
                </>
              )}
            </button>
          </form>

          <div className="mt-6 text-center text-sm" style={{ color: 'rgba(125,211,252,0.45)' }}>
            Already have an account?{' '}
            <Link to="/login" className="font-semibold" style={{ color: '#38bdf8' }}>Sign in</Link>
          </div>
        </div>

        <p className="text-center text-[11px] mt-5" style={{ color: 'rgba(125,211,252,0.25)' }}>
          Built by Akash B · iEZ v2.0 · WABAG Water Treatment
        </p>
      </div>
    </div>
  );
}
