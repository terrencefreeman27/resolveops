# Troubleshooting Accounting Integrations

Lumen syncs invoices and payments with QuickBooks Online and Xero.

## Error codes

- **LL-SYNC-401** — the accounting connection expired. An Owner reconnects it in Settings → Integrations.
- **LL-SYNC-409** — an invoice number already exists in the accounting system. Rename or void the
  duplicate there, then retry the sync.
- **LL-SYNC-429** — the accounting system is rate limiting Lumen. Syncs retry automatically within an hour.

## When to escalate

Escalate to Platform Engineering when a sync keeps failing for more than 4 hours after the first
steps above, or when invoices are missing from the accounting system without any error code.
