import { beforeEach, expect, it, vi } from 'vitest';
import { createClient } from '@supabase/supabase-js';
import { createAuthClient } from './supabaseAuth';

vi.mock('@supabase/supabase-js', () => ({ createClient: vi.fn() }));
beforeEach(() => vi.clearAllMocks());
const config = { apiUrl: 'https://api.example.test', supabaseUrl: 'https://project.supabase.co', publishableKey: 'sb_publishable_test' };

it('keeps tokens in memory, refreshes them, and ignores redirect URL tokens', () => {
  createAuthClient(config);
  expect(createClient).toHaveBeenCalledWith(config.supabaseUrl, config.publishableKey, {
    auth: { persistSession: false, autoRefreshToken: true, detectSessionInUrl: false },
  });
});

it.each(['sb_secret_test', 'service-role-key', 'eyJ.legacy.jwt', ''])('rejects non-publishable keys: %s', key => {
  expect(() => createAuthClient({ ...config, publishableKey: key })).toThrow();
  expect(createClient).not.toHaveBeenCalled();
});

it.each(['http://project.supabase.co', 'https://user:pass@project.supabase.co', 'https://project.supabase.co/auth/v1', 'https://project.supabase.co/?key=value'])('rejects invalid project URLs: %s', supabaseUrl => {
  expect(() => createAuthClient({ ...config, supabaseUrl })).toThrow();
  expect(createClient).not.toHaveBeenCalled();
});
