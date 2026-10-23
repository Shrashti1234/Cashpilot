import React, { useEffect, useState } from 'react';
import type { Session, SupabaseClient } from '@supabase/supabase-js';
import { LogIn, LogOut } from 'lucide-react';
import { createAuthClient, type SupabaseConfig } from './supabaseAuth';
import { WorkspaceOnboarding } from './WorkspaceOnboarding';
import { CustomerManagement, type BusinessWorkspace } from './CustomerManagement';

function BusinessSession({ apiUrl, session }: { apiUrl: string; session: Session }) {
  const [workspace, setWorkspace] = useState<BusinessWorkspace | null>(null);
  return workspace
    ? <CustomerManagement apiUrl={apiUrl} accessToken={session.access_token} workspace={workspace} onBack={() => setWorkspace(null)} />
    : <WorkspaceOnboarding apiUrl={apiUrl} accessToken={session.access_token} onSelect={setWorkspace} />;
}

export function SupabaseSaaS({ config }: { config: SupabaseConfig }) {
  const [client, setClient] = useState<SupabaseClient | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [creatingAccount, setCreatingAccount] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const { apiUrl, supabaseUrl, publishableKey } = config;

  useEffect(() => {
    setLoading(true);
    setSession(null);
    try {
      const authClient = createAuthClient({ apiUrl, supabaseUrl, publishableKey });
      setClient(authClient);
      const { data: { subscription } } = authClient.auth.onAuthStateChange((_event, nextSession) => {
        // The callback stays synchronous: SDK calls here can deadlock its auth lock.
        const valid = nextSession?.expires_at && nextSession.expires_at * 1000 > Date.now();
        setSession(valid ? nextSession : null);
        setLoading(false);
      });
      return () => {
        subscription.unsubscribe();
        authClient.auth.stopAutoRefresh();
      };
    } catch {
      setClient(null);
      setError('Secure sign-in is unavailable. Please contact the workspace administrator.');
      setLoading(false);
    }
  }, [apiUrl, supabaseUrl, publishableKey]);

  useEffect(() => {
    if (!session?.expires_at) return;
    const timer = window.setTimeout(() => {
      setSession(null);
      setMessage('Your session expired. Please sign in again.');
    }, Math.max(0, session.expires_at * 1000 - Date.now()));
    return () => window.clearTimeout(timer);
  }, [session]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!client || busy) return;
    setBusy(true); setError(''); setMessage('');
    try {
      const credentials = { email: email.trim(), password };
      const { data, error: authError } = creatingAccount
        ? await client.auth.signUp(credentials)
        : await client.auth.signInWithPassword(credentials);
      if (authError) throw authError;
      if (creatingAccount && !data.session) {
        setMessage('Check your email to confirm your account, then return here to sign in.');
        setCreatingAccount(false);
      }
    } catch {
      setError(creatingAccount
        ? 'Could not create an account. Check your details and try again.'
        : 'Could not sign in. Check your email and password, and confirm your email if needed.');
    } finally {
      setPassword(''); setBusy(false);
    }
  }

  async function logout() {
    if (!client || busy) return;
    setBusy(true); setError('');
    try {
      const { error: authError } = await client.auth.signOut({ scope: 'local' });
      if (authError) throw authError;
      setSession(null);
    } catch {
      setError('Could not sign out. Please try again.');
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <div className="workspace-screen"><div className="workspace-content" role="status">Establishing secure session…</div></div>;
  if (session) return <>
    <div className="saas-session-bar"><span>Signed in securely</span><button className="workspace-secondary" disabled={busy} onClick={() => void logout()}><LogOut size={16} />Sign out</button></div>
    {error && <div className="error" role="alert">{error}</div>}
    <BusinessSession key={session.user.id} apiUrl={apiUrl} session={session} />
  </>;
  return <div className="workspace-screen">
    <div className="workspace-top"><div className="workspace-brand">CashPilot</div></div>
    <div className="workspace-content auth-content">
      <span className="eyebrow">SECURE WORKSPACE</span>
      <h1>{creatingAccount ? 'Create your account' : 'Welcome to CashPilot'}</h1>
      <p>Manage your businesses, customers and invoices in one place.</p>
      <form className="auth-form" onSubmit={event => void submit(event)}>
        <label htmlFor="auth-email">Email<input id="auth-email" type="email" autoComplete="email" required maxLength={254} value={email} disabled={busy} onChange={event => setEmail(event.target.value)} /></label>
        <label htmlFor="auth-password">Password<input id="auth-password" type="password" autoComplete={creatingAccount ? 'new-password' : 'current-password'} required minLength={creatingAccount ? 8 : undefined} value={password} disabled={busy} onChange={event => setPassword(event.target.value)} /></label>
        {error && <div className="error" role="alert">{error}</div>}
        {message && <p role="status">{message}</p>}
        <button className="primary" disabled={busy || !client} type="submit"><LogIn size={17} />{busy ? 'Please wait…' : creatingAccount ? 'Create account' : 'Sign in'}</button>
        <button className="workspace-secondary" disabled={busy || !client} type="button" onClick={() => { setCreatingAccount(value => !value); setPassword(''); setError(''); setMessage(''); }}>{creatingAccount ? 'Back to sign in' : 'Create an account'}</button>
      </form>
      <p className="auth-note">For your privacy, reloading this page requires signing in again.</p>
    </div>
  </div>;
}
