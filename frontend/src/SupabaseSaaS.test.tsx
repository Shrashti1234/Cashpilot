// @vitest-environment jsdom
import React, { StrictMode } from 'react';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Session } from '@supabase/supabase-js';
import { SupabaseSaaS } from './SupabaseSaaS';

const mocks = vi.hoisted(() => ({
  listener: null as null | ((event: string, session: Session | null) => void),
  signInWithPassword: vi.fn(), signUp: vi.fn(), signOut: vi.fn(),
  unsubscribe: vi.fn(), stopAutoRefresh: vi.fn(), onAuthStateChange: vi.fn(),
}));
vi.mock('./supabaseAuth', () => ({
  createAuthClient: () => ({ auth: mocks }),
}));
vi.mock('./WorkspaceOnboarding', () => ({
  WorkspaceOnboarding: ({ accessToken, onSelect }: { accessToken: string; onSelect: (workspace: unknown) => void }) =>
    <button onClick={() => onSelect({ id: 'business-a', name: 'Business A', mode: 'micro', role: 'owner' })}>Choose workspace with {accessToken}</button>,
}));
vi.mock('./CustomerManagement', () => ({
  CustomerManagement: ({ accessToken }: { accessToken: string }) => <div>Customers with {accessToken}</div>,
}));

const config = { apiUrl: 'https://api.example.test', supabaseUrl: 'https://project.supabase.co', publishableKey: 'sb_publishable_test' };
function session(user = 'alice', token = 'alice-token'): Session {
  return { access_token: token, refresh_token: 'test-refresh', token_type: 'bearer',
    expires_in: 3600, expires_at: Math.floor(Date.now() / 1000) + 3600,
    user: { id: user, aud: 'authenticated', app_metadata: {}, user_metadata: {}, created_at: '' } };
}
function emit(value: Session | null, event = 'SIGNED_IN') {
  act(() => mocks.listener?.(event, value));
}
function enterCredentials() {
  fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'owner@example.test' } });
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'test-password' } });
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.onAuthStateChange.mockImplementation((callback) => {
    mocks.listener = callback;
    callback('INITIAL_SESSION', null);
    return { data: { subscription: { unsubscribe: mocks.unsubscribe } } };
  });
  mocks.signInWithPassword.mockResolvedValue({ data: { session: null }, error: null });
  mocks.signUp.mockResolvedValue({ data: { session: null }, error: null });
  mocks.signOut.mockResolvedValue({ error: null });
});
afterEach(() => { cleanup(); vi.useRealTimers(); });

describe('Supabase workspace authentication', () => {
  it('signs in through Supabase and passes the access token to workspace onboarding', async () => {
    mocks.signInWithPassword.mockImplementation(async () => {
      mocks.listener?.('SIGNED_IN', session());
      return { data: { session: session() }, error: null };
    });
    render(<SupabaseSaaS config={config} />);
    enterCredentials();
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByText('Choose workspace with alice-token')).toBeTruthy();
    expect(mocks.signInWithPassword).toHaveBeenCalledWith({ email: 'owner@example.test', password: 'test-password' });
  });

  it('clears the password and shows a safe message when sign-in fails', async () => {
    mocks.signInWithPassword.mockResolvedValue({ data: { session: null }, error: new Error('internal provider details') });
    render(<SupabaseSaaS config={config} />);
    enterCredentials();
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect((await screen.findByRole('alert')).textContent).toContain('Could not sign in');
    expect(screen.queryByText('internal provider details')).toBeNull();
    expect((screen.getByLabelText('Password') as HTMLInputElement).value).toBe('');
  });

  it('requires email confirmation when signup returns no session', async () => {
    render(<SupabaseSaaS config={config} />);
    fireEvent.click(screen.getByRole('button', { name: 'Create an account' }));
    enterCredentials();
    fireEvent.click(screen.getByRole('button', { name: 'Create account' }));
    expect((await screen.findByRole('status')).textContent).toContain('Check your email');
    expect(mocks.signUp).toHaveBeenCalledWith({ email: 'owner@example.test', password: 'test-password' });
    expect(screen.queryByText(/Choose workspace/)).toBeNull();
  });

  it('propagates refreshed tokens and clears business selection on identity changes', () => {
    render(<SupabaseSaaS config={config} />);
    emit(session());
    fireEvent.click(screen.getByText('Choose workspace with alice-token'));
    expect(screen.getByText('Customers with alice-token')).toBeTruthy();
    emit(session('alice', 'refreshed-token'), 'TOKEN_REFRESHED');
    expect(screen.getByText('Customers with refreshed-token')).toBeTruthy();
    emit(session('bob', 'bob-token'));
    expect(screen.getByText('Choose workspace with bob-token')).toBeTruthy();
    expect(screen.queryByText(/Customers with/)).toBeNull();
  });

  it('signs out only this session and removes the business UI', async () => {
    render(<SupabaseSaaS config={config} />);
    emit(session());
    fireEvent.click(screen.getByRole('button', { name: 'Sign out' }));
    expect(await screen.findByRole('button', { name: 'Sign in' })).toBeTruthy();
    expect(mocks.signOut).toHaveBeenCalledWith({ scope: 'local' });
    expect(screen.queryByText(/Choose workspace/)).toBeNull();
  });

  it('does not claim sign-out succeeded if the provider rejects it', async () => {
    mocks.signOut.mockResolvedValue({ error: new Error('offline') });
    render(<SupabaseSaaS config={config} />);
    emit(session());
    fireEvent.click(screen.getByRole('button', { name: 'Sign out' }));
    expect((await screen.findByRole('alert')).textContent).toContain('Could not sign out');
    expect(screen.getByText('Choose workspace with alice-token')).toBeTruthy();
  });

  it('removes protected content if a session expires without a successful refresh', () => {
    vi.useFakeTimers();
    render(<SupabaseSaaS config={config} />);
    emit({ ...session(), expires_at: Math.floor(Date.now() / 1000) + 1 });
    act(() => { vi.advanceTimersByTime(1100); });
    expect(screen.queryByText(/Choose workspace/)).toBeNull();
    expect(screen.getByText('Your session expired. Please sign in again.')).toBeTruthy();
  });

  it('cleans up auth listeners and refresh timers under StrictMode', () => {
    const view = render(<StrictMode><SupabaseSaaS config={config} /></StrictMode>);
    expect(mocks.unsubscribe).toHaveBeenCalledTimes(1);
    view.unmount();
    expect(mocks.unsubscribe).toHaveBeenCalledTimes(2);
    expect(mocks.stopAutoRefresh).toHaveBeenCalledTimes(2);
  });
});
