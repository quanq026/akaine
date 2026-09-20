# Store and deliver bundles, songs and protected charts

This chapter creates the R2 bucket behind `assets.your-domain`, uploads the
verified resource kit, protects private chart files with a Worker, and caches
large public files at Cloudflare's edge.

At the end:

- public bundles and song resources load from `assets.your-domain`;
- repeated downloads are served from Cloudflare cache;
- direct requests to the private R2 folder return `403`;
- protected files require a short-lived signature from your game server.

## Time and cost

Allow 45–90 minutes plus upload time. Cloudflare Workers, cache rules and Smart
Tiered Cache fit within the Free plan at small-project usage. Leave Argo Smart
Routing and Cache Reserve disabled; they are paid features and are not needed
for this setup.

R2 Standard includes 10 GB-month of storage, one million write operations and
ten million read operations each month. Extra storage costs USD 0.015 per
GB-month. Keep only releases you still need so old duplicate bundles do not
quietly increase the bill.

## You need

- the domain and Cloudflare account from chapter 2;
- the verified resource kit from chapter 4;
- the Cloudflare account owner or an account with R2, Worker, DNS and Cache
  Rules permission;
- the `MY_DOMAIN` value and a short bucket name containing lowercase letters,
  numbers and hyphens.

This chapter uses these examples:

```text
MY_DOMAIN=example.com
ASSET_HOST=assets.example.com
R2_BUCKET=akaine-assets-example
```

## Step 1 — install the upload tool

Open PowerShell as your normal Windows user:

```powershell
winget install --exact --id Amazon.AWSCLI
```

Close and reopen PowerShell, then verify:

```powershell
aws --version
```

The command must print an AWS CLI version instead of “not recognized”. AWS CLI
also works with R2 because R2 provides an S3-compatible upload API.

## Step 2 — create the R2 bucket

1. Open the Cloudflare dashboard.
2. In the left menu, open **R2 Object Storage**.
3. If Cloudflare asks you to enable R2 billing, add a payment method. The free
   monthly allowance is still applied automatically.
4. Select **Create bucket**.
5. Enter a unique bucket name such as `akaine-assets-example`.
6. Choose **Standard** as the storage class.
7. Select **Create bucket**.

Do not enable the `r2.dev` development URL. The guide uses a native R2 Custom
Domain, which supports normal Cloudflare caching and avoids the development
endpoint's variable rate limit.

## Step 3 — create a temporary upload credential

1. In **R2 Object Storage**, select **Manage R2 API Tokens**.
2. Select **Create API token**.
3. Name it `akaine-initial-upload`.
4. Choose **Object Read & Write**.
5. Restrict the token to the bucket you just created.
6. Create the token.
7. Copy the Access Key ID, Secret Access Key and S3 endpoint into your password
   manager. Cloudflare shows the secret only once.

Configure a dedicated AWS CLI profile:

```powershell
aws configure --profile akaine-r2
```

Enter the R2 Access Key ID and Secret Access Key. For the default region enter
`auto`; for output format enter `json`.

Never paste the secret into a GitHub issue, Discord message, screenshot or
command that will be saved in shell history.

## Step 4 — inspect the resource layout before upload

The verified kit contains an `r2` folder with this shape:

```text
r2/
  bundle/                  public, versioned bundle files
  songs/                   public song resources
  private/
    asset-manifest.json    song-to-file allowlist
    songs/                 protected chart/audio files
```

The manifest is a JSON object whose keys are song IDs and whose values are the
only filenames the Worker may return for that song. Do not upload a private
file that is absent from the manifest, and do not add a filename to the
manifest unless the corresponding object exists.

## Step 5 — upload the resource kit

Copy the endpoint from Cloudflare's token page. It looks like:

```text
https://ACCOUNT_ID.r2.cloudflarestorage.com
```

In PowerShell, replace the three example values:

```powershell
$kit = "C:\Akaine\resources\akaine-kit-VERSION\r2"
$bucket = "akaine-assets-example"
$endpoint = "https://ACCOUNT_ID.r2.cloudflarestorage.com"

aws s3 sync $kit "s3://$bucket" `
  --endpoint-url $endpoint `
  --profile akaine-r2
```

List the uploaded top-level objects:

```powershell
aws s3 ls "s3://$bucket" `
  --endpoint-url $endpoint `
  --profile akaine-r2
```

You should see `bundle/`, `songs/` and `private/`. If the upload fails, do not
make the bucket public to work around it. Recheck the endpoint, bucket name and
token scope.

## Step 6 — connect the native R2 Custom Domain

1. Open **R2 Object Storage** and select your bucket.
2. Open **Settings**.
3. Under **Public access**, find **Custom Domains** and select **Connect Domain**.
4. Enter `assets.your-domain`.
5. Confirm the domain and wait until its status becomes **Active**.
6. Confirm that the `r2.dev` development URL remains disabled.

Cloudflare creates the required DNS connection. Do not manually create a CNAME
from your asset hostname to an `r2.dev` hostname.

## Step 7 — create one signing secret

The Worker and game server must use the exact same random secret. Generate it
in PowerShell:

```powershell
$bytes = New-Object byte[] 32
$rng = [Security.Cryptography.RandomNumberGenerator]::Create()
$rng.GetBytes($bytes)
$rng.Dispose()
$assetSecret = [Convert]::ToBase64String($bytes)

New-Item -ItemType Directory -Force C:\Akaine\resources\secrets | Out-Null
Set-Content `
  -LiteralPath C:\Akaine\resources\secrets\asset-signing-secret.txt `
  -Value $assetSecret `
  -NoNewline
```

Store a second copy in your password manager. Do not print the variable or
include the file in Git. A later server chapter will load this same value into
the server environment.

## Step 8 — create the protected-assets Worker

1. In Cloudflare, open **Workers & Pages**.
2. Select **Create** → **Worker**.
3. Name it `akaine-protected-assets` and deploy the starter Worker.
4. Open the new Worker and select **Edit code**.
5. On your computer, copy the public Worker source to the clipboard:

```powershell
Get-Content `
  -LiteralPath C:\Akaine\akaine\cloudflare\protected-assets\worker.mjs `
  -Raw | Set-Clipboard
```

6. Replace the starter code with the clipboard contents and select **Deploy**.

The public Worker source contains no signing secret and no game asset manifest.

## Step 9 — add Worker bindings

Open the Worker → **Settings** → **Bindings** and add:

| Binding type | Variable name | Value |
| --- | --- | --- |
| R2 bucket | `AKAINE_ASSETS` | the bucket created in Step 2 |
| Text variable | `ASSET_MANIFEST_KEY` | `private/asset-manifest.json` |

Then open **Variables and Secrets**, add an encrypted secret named
`ASSET_SIGNING_SECRET`, and paste the value from:

```text
C:\Akaine\resources\secrets\asset-signing-secret.txt
```

Save and deploy the Worker settings.

## Step 10 — attach the protected routes

Open the Worker → **Settings** → **Domains & Routes** → **Add** → **Route**.
Choose your Cloudflare zone and add both routes:

```text
assets.your-domain/private/*
assets.your-domain/protected/songs/*
```

The first route prevents direct access to the private R2 prefix. The second
route accepts only URLs signed by your game server, checks the allowlist, then
reads the approved object from R2.

For performance, the Worker may keep a complete protected file up to 32 MB in
its internal cache for one day. It still verifies the signature before every
cache lookup. Range requests and larger files read directly from R2.

## Step 11 — test the private boundary

Replace the domain and use any song/file name:

```powershell
curl.exe -i "https://assets.example.com/private/songs/test/2.aff"
curl.exe -i "https://assets.example.com/protected/songs/test/2.aff"
```

Both requests must return `403`. The first is blocked because direct private
storage paths are disabled. The second is blocked because it has no server
signature. A `200` response means the private boundary is not working; remove
public access and recheck the Worker routes before continuing.

## Step 12 — create the bundle cache rule

Open your Cloudflare domain → **Rules** → **Cache Rules** → **Create rule**.

Name the rule `Akaine immutable bundles`. Select **Edit expression** and paste,
replacing the hostname:

```text
(http.host eq "assets.example.com" and starts_with(http.request.uri.path, "/bundle/"))
```

Configure:

- Cache eligibility: **Eligible for cache**.
- Edge TTL: **Ignore cache-control header and use this TTL** → 1 year.
- Browser TTL: **Override origin** → 1 year.

Save and deploy the rule. Bundle filenames must include a new version when
their content changes. Never overwrite a cached bundle with different bytes.

## Step 13 — create the public song cache rule

Create a second Cache Rule named `Akaine public songs` with:

```text
(http.host eq "assets.example.com" and starts_with(http.request.uri.path, "/songs/"))
```

Configure:

- Cache eligibility: **Eligible for cache**.
- Edge TTL: **Ignore cache-control header and use this TTL** → 1 month.
- Browser TTL: **Override origin** → 1 day.

This rule does not match `/private/` or `/protected/`.

## Step 14 — enable Smart Tiered Cache

Open the domain → **Caching** → **Tiered Cache** and enable **Smart Tiered
Topology**. This lets one upper-tier Cloudflare location fetch from R2 instead
of every edge location doing so independently.

Leave these optional paid products disabled:

- Cache Reserve;
- Argo Smart Routing.

## Step 15 — verify public caching

Find the bundle manifest filename in the kit's `README.txt`, then run the same
request twice:

```powershell
$url = "https://assets.example.com/bundle/MANIFEST-FILENAME.json"

curl.exe -sS -D headers-1.txt -o NUL --range 0-31 $url
curl.exe -sS -D headers-2.txt -o NUL --range 0-31 $url

Select-String -Path headers-1.txt,headers-2.txt -Pattern `
  "HTTP/","CF-Cache-Status","Content-Range","Cache-Control"
```

The response should be `206 Partial Content`, include a `Content-Range`, and
eventually show `CF-Cache-Status: HIT`. The first request may show `MISS` while
Cloudflare fills the cache. If the second request is not a HIT, wait a short
time and repeat before changing the rules.

## API requests must not use these cache rules

The `api.your-domain` hostname is dynamic: login, account and score responses
must never be cached. Do not create a “Cache Everything” rule for the API host.
The server chapter will configure `Cache-Control: private, no-store`; after the
server is running, API responses should show `CF-Cache-Status: DYNAMIC`.

## Updating a release later

- Publish new bundle content under a new versioned filename.
- Do not overwrite a one-year cached bundle filename.
- If a public song object must be replaced at the same URL, open **Caching** →
  **Configuration** → **Purge Cache** → **Custom Purge** and purge only the
  changed URL.
- Update `private/asset-manifest.json` together with private objects. A file not
  declared in the manifest remains inaccessible.

## Step 16 — revoke the temporary upload credential

After the initial upload and cache tests pass:

1. Open **R2 Object Storage** → **Manage R2 API Tokens**.
2. Revoke `akaine-initial-upload`.
3. Open `%USERPROFILE%\.aws\credentials` in Notepad.
4. Remove only the `[akaine-r2]` section and its two key lines. Do not delete
   another profile you use for unrelated AWS work.

Create a new short-lived bucket-scoped token when you intentionally publish an
update. Revoke any token immediately if it appears in a screenshot, terminal
log or repository.

## How to know this chapter is complete

- The R2 bucket contains `bundle/`, `songs/` and `private/`.
- `assets.your-domain` is an Active R2 Custom Domain.
- The `r2.dev` development URL is disabled.
- Direct private and unsigned protected requests return `403`.
- The Worker has the R2 binding, manifest-key variable and signing secret.
- Bundle requests support Range and become cache `HIT`.
- Smart Tiered Cache is enabled.
- Cache Reserve and Argo are disabled.
- The temporary upload token and local `akaine-r2` profile are removed.

The next chapter will install the game server and give it the same asset
signing secret, allowing it to create valid protected download URLs.
