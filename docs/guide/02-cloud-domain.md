# Create the cloud server and connect a domain

This chapter creates the accounts and infrastructure that Akaine will use. At
the end, you will be able to connect to a Linux server with a fixed public IP,
and `api.your-domain` will resolve to that IP through Cloudflare.

## Time and cost

Plan for 45–90 minutes, plus any account-verification waiting time.

If you are a new AWS customer, select the Free plan during registration when
it is available to you. AWS currently gives new customers USD 100 in credits
at sign-up and allows them to earn up to USD 100 more, with the free plan
lasting up to six months or until the credits are used. The Lightsail server
in this guide has a list price of USD 12/month, so the credits can cover the
initial learning period.

Vietnamese citizens aged 18–23 can register one `.id.vn` domain free for two
years. iNET is one of the participating `.vn` registrars and verifies eligibility
with eKYC. If you do not qualify, iNET and other registrars often offer cheap
promotional domains starting around 40,000 VND; always check both the first-year
and renewal price before buying.

Cloudflare DNS, CDN and SSL are free. R2 Standard includes 10 GB-month of
storage, one million write operations and ten million read operations each
month. Extra storage is USD 0.015 per GB-month and Internet egress from R2 is
free. A small Akaine deployment will commonly stay below USD 1/month for R2.

After six months, you can upgrade AWS to paid use, move to another VPS provider,
or shut the server down. Export your server and database before the AWS free
plan expires; an expired free-plan account can become inaccessible.

## You need

- an email address you control;
- a phone number for account verification;
- a payment card accepted by AWS and your registrar;
- a password manager;
- an AWS account eligible for credits or a payment method for later paid use.

## Step 1 — create and secure the Cloudflare account

1. Open `dash.cloudflare.com` in your browser.
2. Select **Sign up**.
3. Enter the project email address and a unique password.
4. Verify the email Cloudflare sends you.
5. In the dashboard, open your profile menu, then **My Profile** →
   **Authentication**.
6. Enable two-factor authentication. An authenticator app is preferable to SMS.
7. Save the recovery codes in your password manager or an offline backup.

Do not continue until you can sign out and sign back in using two-factor
authentication.

## Step 2 — register the domain

### Free `.id.vn` through iNET

Use this option if you are a Vietnamese citizen aged 18–23 and have not already
claimed the free `.id.vn` offer.

1. Open iNET OnePortal and choose the free `.id.vn` registration service.
2. Sign in or create an iNET account.
3. Complete eKYC using your own identity document and face verification.
4. Search for the `.id.vn` name you want.
5. Complete the owner declaration and submit the registration.
6. Wait for the domain status to become active in iNET.

Each eligible person can receive one free `.id.vn`, so choose the name carefully.
The current program covers the domain for two years. Before that period ends,
check the renewal terms or prepare to move to another domain.

### Paid domain

If you are not eligible, purchase the least expensive suitable domain from iNET
or another registrar. Promotional prices can be around 40,000 VND, but the
renewal price can be different. Avoid choosing a domain only because its first
year is cheap.

Write your real domain here before continuing:

```text
MY_DOMAIN=____________________________
```

## Step 3 — connect the domain to Cloudflare

1. In the Cloudflare dashboard, open **Websites** and select **Add a domain**.
2. Enter the domain you registered and choose the Free plan.
3. Cloudflare scans existing DNS records. Continue to the nameserver page.
4. Cloudflare shows two assigned nameservers. Keep this page open.
5. In iNET or your registrar's domain-management page, replace the existing
   nameservers with the two Cloudflare nameservers.
6. Return to Cloudflare and select **Check nameservers now**.

If DNSSEC is already enabled at the registrar, disable it before changing
nameservers. Enable DNSSEC again in Cloudflare only after the zone is active.

### How to know it worked

Open the domain in Cloudflare. The Overview page must say **Active**, not
“Pending nameserver update”. Do not create production records while the zone is
pending.

## Step 4 — create and secure the AWS account

1. Open `aws.amazon.com` and select **Create an AWS Account**.
2. Complete email verification, contact information, payment verification and
   phone verification.
3. Choose the AWS Free plan if it is offered and you are using the six-month
   credit period. Choose the paid plan only if you need services unavailable on
   the free plan or want the server to continue after the free period.
4. Sign in to the AWS Management Console as the account owner.
5. Open the account menu → **Security credentials**.
6. Enable MFA for the root user and store the recovery information safely.
7. Open **Billing and Cost Management** and confirm the credit balance and its
   expiration date.
8. If you chose the paid plan, open **Budgets** → **Create budget** and create a
   USD 20 monthly budget with email alerts at 50%, 80% and 100%.

Never create an access key for the AWS root user. Browser administration and
automation credentials will be handled separately.

## Step 5 — create the Lightsail server

1. In the AWS Console search bar, enter `Lightsail` and open it.
2. Select **Create instance**.
3. Under **Instance location**, choose the region nearest most players. For a
   Vietnam/Southeast Asia audience, choose **Singapore**.
4. Select **Linux/Unix**.
5. Select **OS Only**, then choose **Ubuntu 24.04 LTS**.
6. Under the instance plan, select the Linux plan with:
   - public IPv4;
   - 2 GB RAM;
   - 2 vCPUs;
   - 60 GB SSD;
   - USD 12/month at the time this guide was written.
7. Enter `akaine-server` as the instance name.
8. Select **Create instance**.

Wait until the instance status becomes **Running**.

## Step 6 — create a fixed IP address

The default public IPv4 can change after a stop/start. DNS must point to an
address that stays the same.

1. In Lightsail, open **Networking** from the left menu.
2. Select **Create static IP**.
3. Choose the same Singapore region.
4. Attach it to `akaine-server`.
5. Name it `akaine-server-ip` and select **Create**.
6. Copy the IPv4 address into your password manager or setup notes.

```text
SERVER_IP=____________________________
```

## Step 7 — download your SSH key

1. In Lightsail, open **Account** → **SSH keys**.
2. Under the Singapore region, download the default private key.
3. Move the downloaded `.pem` file to a private folder of your choice.
4. Never upload this file to GitHub, Discord or cloud storage without strong
   encryption.

## Step 8 — configure the Lightsail firewall

Open `akaine-server` → **Networking** → **IPv4 Firewall**. Remove broad SSH
access and create these rules:

| Purpose | Protocol | Port | Allowed source |
| --- | --- | --- | --- |
| SSH administration | TCP | 22 | Your current public IPv4 followed by `/32` |
| Web redirect | TCP | 80 | All IPv4 addresses |
| HTTPS API | TCP | 443 | All IPv4 addresses |
| Link Play | UDP | 10900 | All IPv4 addresses, only if you enable Link Play |
| Link Play | TCP | 10901 | All IPv4 addresses, only if you enable Link Play |

To find your current public IPv4, search `what is my IP` in your browser. If it
shows `203.0.113.10`, enter `203.0.113.10/32`. When your home IP changes, update
this rule before attempting SSH again.

## Step 9 — test SSH from Windows

Open PowerShell and replace `YOUR_SERVER_IP`:

```powershell
$sshKey = Get-Item (Read-Host "Full path to the downloaded SSH private key")
ssh -i $sshKey.FullName ubuntu@YOUR_SERVER_IP
```

The first connection asks whether you trust the server fingerprint. Confirm
only if the IP is the static IP you just created. A successful connection ends
at a prompt similar to:

```text
ubuntu@ip-172-xx-xx-xx:~$
```

Type `exit` to return to Windows.

If the connection times out, check that the SSH firewall rule contains your
current public IP. Do not solve the problem by opening port 22 to the entire
Internet.

## Step 10 — create the first DNS records

Return to Cloudflare and open your domain → **DNS** → **Records**. Create:

| Type | Name | Content | Proxy status | TTL |
| --- | --- | --- | --- | --- |
| A | `api` | your Lightsail static IP | DNS only | Auto |
| A | `link` | your Lightsail static IP | DNS only | Auto |

Leave both records DNS-only for now. The grey cloud means Cloudflare publishes
the DNS answer but does not proxy traffic. `link` will remain DNS-only because
Link Play uses TCP/UDP ports that the normal HTTPS proxy does not carry. The
server-install chapter will turn `api` orange after HTTPS is configured.

Do not create `assets` yet. It will be attached directly to an R2 bucket after
the resource kit is prepared.

## Step 11 — verify DNS from Windows

Close and reopen PowerShell, then replace the example domain:

```powershell
nslookup api.example.com 1.1.1.1
nslookup link.example.com 1.1.1.1
```

Both commands should show the Lightsail static IP. DNS changes often appear in
minutes, but cached records can take longer.

## How to know this chapter is complete

- Cloudflare shows the domain as Active.
- AWS MFA and Cloudflare two-factor authentication are enabled.
- The AWS credit balance/expiration is recorded, or a USD 20 paid-plan budget
  alert exists.
- `akaine-server` is Running in Singapore on the 2 GB plan.
- A static IPv4 is attached.
- SSH succeeds only from your allowed IP.
- `api.your-domain` and `link.your-domain` resolve to the static IP.

## How to undo this chapter

If you stop here and do not want ongoing server charges:

1. Delete the Lightsail instance.
2. Delete the static IP after the instance is gone.
3. Remove the `api` and `link` DNS records.
4. Cancel or disable domain auto-renewal if you no longer want the domain.

Deleting only the instance does not automatically remove every attached or
reserved resource. Check the Lightsail Networking and Snapshots pages before
considering cleanup complete.

Next: [Prepare your Windows computer](03-workstation.md).
