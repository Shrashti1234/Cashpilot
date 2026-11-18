# Supabase database trust root

`supabase-root-2021.crt` is a public CA certificate, not a private key or secret.
It was downloaded over HTTPS from Supabase's certificate distribution endpoint:

https://supabase-downloads.s3-ap-southeast-1.amazonaws.com/prod/ssl/prod-ca-2021.crt

- Subject: Supabase Root 2021 CA / Supabase Inc
- SHA-256: `807025ad50d4ed219d2c9c7d299c004f824eb00cf7f65afef607d07b72e6cafa`
- Expiry: 26 April 2031

Use `sslmode=verify-full&sslrootcert=/app/certs/supabase-root-2021.crt`
in the Docker runtime's database URL. The shared pooler uses Supabase's CA;
the ordinary system trust store alone does not validate that chain.
Do not turn off certificate verification to fix a missing CA file.

See https://supabase.com/docs/guides/platform/ssl-enforcement for provider guidance.
