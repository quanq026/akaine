# Akaine External Read-Only API (`v1`)

Read-only HTTP JSON API for community Discord bots, web score trackers, and dashboards built around an Akaine server.

All database connections open SQLite with `mode=ro` and `PRAGMA query_only = ON`. There are **no** account, login, password, ticket, or write endpoints exposed here.

---

## 1. Getting a Personal Developer Key

In the Discord server where Demiurge is running:

1. Link or create your Akaine account first using `/link` or `/create`.
2. Run `/dev_key` with **Action = `Generate / Rotate key`** (optionally add a `label` up to 40 characters).
3. Copy your token (`akdev_...`) from the ephemeral reply — **it is shown once**. Running generate again replaces your previous personal key.
4. Use `/dev_key action:Status` to check key metadata or `/dev_key action:Revoke key` to revoke your key immediately.

---

## 2. Authentication & Base URL

- **Base URL:** `https://api.example.com/external/v1` *(check `/dev_key` output for this server's live URL)*
- **Header:**

```http
Authorization: Bearer <your_dev_token>
```

Tokens cannot contain whitespace and are stored as SHA-256 hashes server-side.

---

## 3. Rate Limits & Privacy Rules

| Rule | Community key (`akdev_...`) |
| --- | --- |
| Scope header | `X-External-API-Scope: community` |
| Rate limit | `60` requests per `60` seconds (per key) |
| Rate limit headers | `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `Retry-After` on `429` |
| Profile privacy | Only returns accounts where `is_profile_public = 1` |
| Hidden rating | Sets `rating_ptt = -1` when `is_hide_rating = 1` |
| Static assets (`/assets/*`) | Disabled (`403 assets_forbidden_for_community_key`) |

Every response also sets `Cache-Control: private, no-store` and `X-Content-Type-Options: nosniff`.

---

## 4. Endpoints

All list endpoints support pagination query parameters:
- `limit`: integer `1..200` (default `100`)
- `offset`: integer `0..1000000` (default `0`)

### `GET /external/v1`
Returns API version, current key scope/rate-limit settings, and available resources.

### `GET /external/v1/players`
Returns public player profiles sorted by `user_id`.
- **Columns:** `user_id`, `name`, `join_date`, `user_code`, `rating_ptt`, `character_id`, `is_char_uncapped`, `is_char_uncapped_override`, `is_hide_rating`, `song_id`, `difficulty`, `score`, `shiny_perfect_count`, `perfect_count`, `near_count`, `miss_count`, `health`, `modifier`, `time_played`, `clear_type`, `rating`, `is_profile_public`, `showcase_characters`

### `GET /external/v1/best-scores`
Returns Best scores from `best_score` for public players, sorted by `rating DESC`.
- **Optional filter:** `user_code` (exactly 9 digits, e.g. `?user_code=123456789`)
- **Columns:** `user_id`, `song_id`, `difficulty`, `score`, `shiny_perfect_count`, `perfect_count`, `near_count`, `miss_count`, `health`, `modifier`, `time_played`, `best_clear_type`, `clear_type`, `rating`, `score_v2`

### `GET /external/v1/recent-scores`
Returns Recent 30 entries (`recent30`) for public players, sorted by `time_played DESC`.
- **Optional filter:** `user_code` (exactly 9 digits)
- **Columns:** `user_id`, `r_index`, `time_played`, `song_id`, `difficulty`, `score`, `shiny_perfect_count`, `perfect_count`, `near_count`, `miss_count`, `health`, `modifier`, `clear_type`, `rating`

### `GET /external/v1/plays`
Returns chronological play logs (`user_score`) for public players, sorted by `time_played DESC`.
- **Optional filter:** `user_id` (non-negative integer)
- **Columns:** `user_id`, `song_id`, `difficulty`, `time_played`, `score`, `shiny_perfect_count`, `perfect_count`, `near_count`, `miss_count`, `health`, `modifier`, `clear_type`, `rating`

### `GET /external/v1/charts`
Returns chart metadata and constants (`rating * 10`, `-1` if unavailable; values <= `-10` in fan catalogs indicate invalid/unset difficulties).
- **Optional filter:** `song_id` (`[A-Za-z0-9_-]{1,80}`)
- **Columns:** `song_id`, `name`, `rating_pst`, `rating_prs`, `rating_ftr`, `rating_byn`, `rating_etr`

---

## 5. Quick-Start Examples

### cURL

```bash
curl -H "Authorization: Bearer <your_dev_token>" \
  "https://api.example.com/external/v1/best-scores?user_code=123456789&limit=30"
```

### Python (`urllib`)

```python
import json
import urllib.request

BASE_URL = "https://api.example.com/external/v1"
TOKEN = "<your_dev_token>"

req = urllib.request.Request(
    f"{BASE_URL}/players?limit=50&offset=0",
    headers={"Authorization": f"Bearer {TOKEN}"},
)
with urllib.request.urlopen(req, timeout=15) as resp:
    payload = json.loads(resp.read().decode("utf-8"))
print(f"Loaded {payload['count']} public players")
```

### JavaScript (`fetch`)

```js
const BASE_URL = "https://api.example.com/external/v1";
const TOKEN = "<your_dev_token>";

const res = await fetch(`${BASE_URL}/recent-scores?user_code=123456789&limit=10`, {
  headers: { Authorization: `Bearer ${TOKEN}` },
});
if (!res.ok) throw new Error(`API error ${res.status}`);
const { data } = await res.json();
console.log(data);
```

---

## 6. Error Codes

| HTTP Status | `error` | Meaning |
| --- | --- | --- |
| `400` | `invalid_pagination`, `invalid_user_code`, `invalid_song_id`, `invalid_query` | Invalid query parameter |
| `401` | `unauthorized` | Missing/invalid Bearer token or banned developer key |
| `403` | `assets_forbidden_for_community_key` | Static asset endpoints are restricted for community keys |
| `429` | `rate_limited` | Per-key rate limit exceeded; honor `Retry-After` header |
| `503` | `api_unavailable` | Key database temporarily unavailable |
