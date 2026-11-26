# mw-rid Identity Contract (mw-core)

**Derived from:** `Z:\repo\mw-rid` OIDC implementation, ADR-001, and `workspace.json` service metadata.

**Profile:** `id`  
**Port:** `4480`  
**Stack:** `TypeScript/Node`  
**Pillar:** Sovereign Identity Provider (OIDC/PKCE)

## OIDC Endpoints

| Endpoint | Method | Path | Description |
|---|---|---|---|
| `.well-known/openid-configuration` | `GET` | `/.well-known/openid-configuration` | OIDC discovery document |
| `jwks` | `GET` | `/jwks` | JSON Web Key Set for token verification |
| `auth` | `GET` | `/auth` | Authorization endpoint (PKCE) |
| `token` | `POST` | `/token` | Token endpoint |
| `me` | `GET` | `/me` | Userinfo endpoint |
| `token/revocation` | `POST` | `/token/revocation` | Token revocation |
| `/health` | `GET` | `/health` | Health check |

## Authentication Contracts

- **Mandatory PKCE** `S256` for public clients
- **Exact redirect URI** allowlist
- **Rotating refresh tokens** with replay detection
- **`client_credentials`** machine grants supported
- **Asymmetric RS256 signing only** (fails closed in `NODE_ENV=production` without `MW_RID_SIGNING_KEY_PEM` or `MW_RID_SIGNING_KEY_PATH`)

## Bootstrap (Platform Owner Onboarding)

- `POST /api/bootstrap` — atomic one-time Platform Owner bootstrap
  - Requires `setupSecret`, `username`, `password` (min 8 chars), optional `email`
  - SHA-256 verifier hash, disabled immediately on first use
  - Returns: `{ sub, username, role, status }`
  - Idempotent: returns `bootstrap_consumed` on second call

## Identity API

| Endpoint | Method | Description |
|---|---|---|
| `/api/accounts` | `POST` | Creates active account with scrypt salted password hash |
| `/api/service-principals` | `POST` | Registers OAuth2 client_credentials machine clients |
| `/api/outbox` | `GET` | Lists transactional identity_outbox events |
| `/api/outbox/:id/ack` | `POST` | Acks an outbox event |

## Token Verification (`@moonwitness/rid-sdk`)

- `verifyAccessToken({ token, issuer, audience, jwksUri })` — enforces `iss`, `aud`, `exp`, algorithm allowlist (`RS256`, `RS384`, `RS512`, `PS256`, `PS384`, `PS512`, `ES256`, `ES384`, `ES512`, `EdDSA`), rejects OIDC ID tokens
- `createPkcePair()` & `buildAuthorizationUrl(...)` — PKCE S256 helpers for `mw-board`, `mw-echo`, `mw-mylove`
- Zero private keys — resource-server verification only

## Dependencies

- `MW_RID_PORT` — port (default 4480)
- `MW_RID_ISSUER` — issuer URL (default `https://id.<MW_DOMAIN>`)
- `MW_RID_DB_PATH` — SQLite persistence path
- `MW_RID_BOOTSTRAP_SECRET` — bootstrap setup secret
- `MW_RID_COOKIE_SECRET` — cookie signing secret
- `MW_RID_SIGNING_KEY_PEM` — RSA/PEM signing key (required for production)
- `MW_RID_SIGNING_KEY_PATH` — path to signing key file