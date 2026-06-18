import { Component, ReactNode } from 'react';
import { RefreshCw } from 'lucide-react';

interface Props { children: ReactNode; }
interface State { hasError: boolean; message: string; }

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, message: '' };

  static getDerivedStateFromError(err: Error): State {
    return { hasError: true, message: err?.message || 'Unknown error' };
  }

  render() {
    if (!this.state.hasError) return this.props.children;
    return (
      <div className="min-h-screen flex items-center justify-center p-8" style={{ background: 'var(--s0)' }}>
        <div className="max-w-md w-full rounded-2xl p-8 text-center" style={{ background: 'var(--s2)', border: '1px solid rgba(248,113,113,0.2)' }}>
          <div className="w-14 h-14 rounded-2xl flex items-center justify-center mx-auto mb-5" style={{ background: 'rgba(248,113,113,0.1)', border: '1px solid rgba(248,113,113,0.25)' }}>
            <span className="text-2xl">⚠</span>
          </div>
          <h2 className="text-lg font-bold mb-2" style={{ color: 'var(--t0)' }}>Something went wrong</h2>
          <p className="text-sm mb-6" style={{ color: 'var(--t2)' }}>{this.state.message}</p>
          <button
            onClick={() => { this.setState({ hasError: false, message: '' }); window.location.reload(); }}
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold"
            style={{ background: 'var(--em-dim)', color: 'var(--em-lt)', border: '1px solid var(--em)' }}
          >
            <RefreshCw className="w-4 h-4" /> Reload page
          </button>
        </div>
      </div>
    );
  }
}
