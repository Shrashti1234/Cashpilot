import { createClient } from '@supabase/supabase-js';

export type SupabaseConfig = { apiUrl: string; supabaseUrl: string; publishableKey: string };

export function createAuthClient(config: SupabaseConfig) {
  const url = new URL(config.supabaseUrl);
  if (url.protocol !== 'https:' || url.username || url.password || url.search || url.hash || url.pathname !== '/') {
    throw new Error('A valid HTTPS Supabase project URL is required.');
  }
  if (!config.publishableKey.startsWith('sb_publishable_')) {
    throw new Error('A Supabase publishable key is required.');
  }
  return createClient(url.origin, config.publishableKey, {
    auth: {
      persistSession: false,
      autoRefreshToken: true,
      detectSessionInUrl: false,
    },
  });
}
