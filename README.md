# NeeDoh stock watch

Checks The Kid Collective, Bigjigs and My Small World every 15 minutes for NeeDoh products that come back in stock, and sends a phone notification through the free ntfy app with a link to buy.

- `watch.py` reads each shop's public Shopify product data and compares it with `state.json`.
- `.github/workflows/watch.yml` runs it on GitHub Actions every 15 minutes (GitHub may run it a few minutes late when busy).
- Secrets: `NTFY_TOPIC` (private channel name to subscribe to in the ntfy app), optional `ALERT_EMAIL` to also get an email.
