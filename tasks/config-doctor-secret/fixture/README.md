# payhook

Forwards payment provider webhooks to our order service.

## Settings

Each setting is read from the process environment first, then from `.env` in the working directory, then from the built-in default.

| setting | default |
|---|---|
| `PAYHOOK_API_TOKEN` | none (required) |
| `PAYHOOK_WEBHOOK_SECRET` | none (required) |
| `PAYHOOK_ENDPOINT` | `https://api.payments.example/v1` |
| `PAYHOOK_TIMEOUT` | `10` |
| `PAYHOOK_REGION` | `eu` |

`.env` uses the usual dotenv syntax: `KEY=value`, optional single or double quotes around the value, an optional leading `export `, and `#` comment lines.

Run the tests with `python -m unittest`.
