# 🤖 Personal AI Browser Agent — $0 forever

A personal website with an AI agent that uses a **real, visible browser** like a human:
browse, book, fill forms, and log in to sites. You **watch the browser live** in the
page, and **take over** with one tap whenever the agent gets stuck (captchas, logins,
2FA) — then hand control back.

**Total cost: $0.** Free Oracle Cloud VM + free Gemini API key + free DuckDNS domain.
No credit card charges anywhere if you follow the steps below.

---

## How it works

```
Your phone
   │  https://your-name.duckdns.org
   ▼
┌─────────┐
│  Caddy  │  automatic HTTPS (Let's Encrypt)
└──┬──┬───┘
   │  │  └─ /vnc/*  → live browser view (behind your site login)
   │  └──── /api/*  → agent backend
   └─────── /       → website UI
        ┌────────┐   ┌──────────┐   ┌─────────┐
        │  web   │   │  agent   │   │ browser │
        │ (nginx)│   │(FastAPI +│   │ headed  │
        └────────┘   │browser-  │   │Chromium │
                     │ use AI)  │──▶│ + noVNC │
                     └──────────┘   └─────────┘
                         │  controls via CDP      ▲ you watch & take over
                         │  one task at a time    │ persistent profile volume
                                                  │ (your logins survive restarts)
```

- **browser** — headed Chromium under Xvfb, streamed to your page with noVNC.
  The Chromium profile lives in a Docker volume, so sites you log in to **manually**
  stay logged in after restarts. The agent reuses that same session.
- **agent** — Python + [browser-use](https://github.com/browser-use/browser-use) (open
  source, MIT) driven by a free Gemini model. One task at a time; pause / resume /
  cancel; auto-pauses and asks for your help on likely bot-checks.
- **web** — mobile-first UI: chat box, live browser viewer, Take over / Hand back buttons.
- **caddy** — reverse proxy with automatic HTTPS.

---

## What you need (all free)

1. An **Oracle Cloud** account (Always Free tier — asks for a credit card for
   verification only; the free tier costs nothing).
2. A free **DuckDNS** subdomain (5 minutes, from your phone browser).
3. A free **Gemini API key** from Google AI Studio (no credit card).
4. A **GitHub** account to hold this project's files.
5. An SSH app on your phone (e.g. **Termius**, free) — or Oracle's browser-based Cloud Shell.

---

## Step 1 — Create the free VM on Oracle Cloud (phone browser)

1. Go to [cloud.oracle.com](https://cloud.oracle.com) and sign up. **Important:**
   Oracle asks for a credit card to verify your identity. The **Always Free** resources
   below cost $0 — just **never change the shape to a paid one** and never enable
   "paid" upgrades. Set up billing alerts if it makes you feel safer.
2. In the Oracle console, go to **Compute → Instances → Create instance**.
3. Settings:
   - **Name:** anything, e.g. `browser-agent`
   - **Image:** Ubuntu **24.04** — make sure you pick the **aarch64 / ARM** build
     (the Ampere shape only runs ARM images).
   - **Shape:** click *Change shape* → **VM.Standard.A1.Flex** (Ampere ARM).
     Set **4 OCPUs** and **24 GB RAM** — this is the free allowance (4/24 max).
   - **Networking:** keep the defaults (a new VCN is fine). Note the **public IP**
     after creation.
   - **SSH keys:** choose *Generate a key pair* and **save the private key** —
     you'll import it into Termius on your phone.
4. Click **Create**. If you get an **"Out of capacity"** error, that's normal on the
   free tier — try a different region (home region is set at signup; common ones with
   capacity: `us-ashburn-1`, `eu-frankfurt-1`, `ap-mumbai-1`). Keep trying; it
   usually works within a day.
5. Open the network for the web: go to **Networking → Virtual Cloud Networks →
   your VCN → Security Lists → Default Security List → Add Ingress Rules** and add:
   - Source `0.0.0.0/0`, TCP, destination port **80**
   - Source `0.0.0.0/0`, TCP, destination port **443**
   - (SSH port 22 is already open.)
   
   The setup script also opens these ports in the VM's own firewall automatically.

> ⚠️ **Cost safety:** Stay on `VM.Standard.A1.Flex` with ≤4 OCPUs / ≤24 GB RAM.
> That's inside Always Free. Anything else (other shapes, "paid" toggles) can bill you.

## Step 2 — Get a free domain on DuckDNS (5 minutes, phone browser)

1. Go to [duckdns.org](https://www.duckdns.org) and sign in (Google/GitHub/etc.).
2. Under **"Add a domain"**, type a name like `adam-agent` → **Add domain**.
   Your address is now `adam-agent.duckdns.org`.
3. Click the **IP field** next to your domain and type your VM's **public IP**
   (from Step 1), then **update**. (DuckDNS calls it "current ip" — just overwrite it.)
4. Done. If your VM's IP ever changes (it can if you stop/start the instance), update
   it here again — or add this cron line on the VM to auto-update (replace the
   placeholders):
   ```
   */5 * * * * curl -sk "https://www.duckdns.org/update?domains=adam-agent&token=YOUR-TOKEN&ip=" >/dev/null 2>&1
   ```
   (Your token is shown at the top of the DuckDNS page after sign-in.)

## Step 3 — Get a free Gemini API key (phone browser)

1. Go to [aistudio.google.com](https://aistudio.google.com) and sign in with Google.
2. Click **Get API key** → **Create API key**. No credit card needed.
3. Copy the key somewhere safe (your notes app). You'll paste it into the setup script.

> Free-tier notes (checked Oct 2026 — Google changes these, your AI Studio dashboard
> shows your live limits): roughly **~15 requests/minute** and a few hundred requests
> per day for Flash models. One agent task uses ~1–2 requests per browser step, so
> this is plenty for personal use. If you hit a `429` error, just wait a bit.
> Also note: Google may use free-tier API data to improve its products — don't run
> tasks involving highly sensitive personal data on the free tier.

## Step 4 — Put this project on GitHub (phone browser)

1. On [github.com](https://github.com) (signed in), tap **+ → New repository**.
   Name it `browser-agent`, leave it **Public** (or Private — your choice), tap
   **Create repository**.
2. On the repo page tap **Add file → Upload files** and upload **everything** in this
   folder (`docker-compose.yml`, `.env.example`, `setup.sh`, `README.md`, and the
   `browser/`, `agent/`, `web/`, `caddy/` folders). Tap **Commit changes**.
3. Copy your repo URL — you'll need it in Step 6. It looks like:
   `https://github.com/YOUR-USERNAME/browser-agent.git`

## Step 5 — SSH into the VM from your phone

**Option A — Termius (recommended):** install Termius, create a new Host with your
VM's public IP, username `ubuntu`, and import the private key you saved in Step 1.

**Option B — Oracle Cloud Shell:** in the Oracle console (phone browser) click the
**Cloud Shell** icon (`>_` in the top bar). In Cloud Shell, paste your private key
into a file and SSH:
```
cat > ~/.ssh/oci_key   # paste the key, then Ctrl+D
chmod 600 ~/.ssh/oci_key
ssh -i ~/.ssh/oci_key ubuntu@YOUR-VM-PUBLIC-IP
```

## Step 6 — Run the one-line setup

Paste this into the SSH session (replace the URL with **your** repo):

```bash
curl -fsSL https://raw.githubusercontent.com/YOUR-USERNAME/browser-agent/main/setup.sh -o /tmp/setup.sh && sudo bash /tmp/setup.sh
```

The script will:
1. Install Docker (if missing) and `git`.
2. Open ports 80/443 in the VM firewall.
3. Clone your repo to `/opt/browser-agent`.
4. Ask you for: **repo URL** (if not passed), **domain** (`adam-agent.duckdns.org`),
   **site password**, **Gemini API key**, **model** (just press Enter for the default).
5. Build the images (first build takes ~5–10 minutes on the free VM) and start everything.

You can pass the repo URL non-interactively if you like:
```bash
curl -fsSL https://raw.githubusercontent.com/YOUR-USERNAME/browser-agent/main/setup.sh -o /tmp/setup.sh && sudo REPO_URL=https://github.com/YOUR-USERNAME/browser-agent.git bash /tmp/setup.sh
```

## Step 7 — Open your site and log in to your accounts

1. Wait a minute, then open **`https://adam-agent.duckdns.org`** (your subdomain)
   on your phone. Log in with the site password you chose.
2. You'll see the **live browser**. Tap **✋ Take over** — now you can tap and type
   in the browser yourself.
3. Visit the sites you want the agent to use (email, airline, shops…) and **log in
   manually, yourself**. Your logins are saved in the browser's persistent profile —
   the agent will reuse them, and **no password is ever stored in any config file**.
4. Tap **🤖 Hand back to agent** when you're done.

## Step 8 — Give the agent its first task

Type a task in the chat box, e.g.:

> *Go to google.com/flights and find the cheapest round trip from Winnipeg to Toronto
> next month, then tell me the price and airline.*

Tap **▶ Start task** and watch it work in the live browser view.

---

## The human-takeover flow (captchas & co.)

- While the agent works, the browser view is **watch-only**.
- If the agent hits something that looks like a bot check (captcha, "verify you are
  human", unusual-traffic page), it **pauses automatically** and shows a
  **"🙋 The agent needs your help"** banner.
- Tap **✋ Take over**, solve the captcha / finish the login yourself in the browser,
  then tap **🤖 Hand back to agent** — it resumes where it left off.
- You can also take over manually at any time, even mid-task.

**Honest note:** no setup defeats every anti-bot system. This project uses a real
headed Chromium with basic stealth (realistic user-agent/viewport/timezone,
`AutomationControlled` blink feature disabled), but some sites will still challenge
automation — that's exactly what the takeover flow is for.

---

## Troubleshooting

| Problem | What to do |
|---|---|
| Site doesn't load / certificate error | DNS takes a few minutes to propagate. Check your DuckDNS IP matches the VM IP. Check Caddy logs: `docker compose -f /opt/browser-agent/docker-compose.yml logs caddy` |
| Browser view is black / "can't connect" | The browser container may still be starting (Chromium takes ~30–60s). Check: `docker compose -f /opt/browser-agent/docker-compose.yml logs browser`. The agent waits for it automatically. |
| Agent says `429` / rate limit | You hit the Gemini free-tier quota. Wait a few minutes (limits reset). Reduce `MAX_STEPS` in `.env` if it happens often. |
| Agent error about API key | Make sure `LLM_API_KEY` in `/opt/browser-agent/.env` is correct, then `docker compose -f /opt/browser-agent/docker-compose.yml up -d agent`. |
| Agent is stuck / going in circles | Tap **⏹ Cancel**, or **✋ Take over** and do the tricky part yourself, then **🤖 Hand back**. |
| "409 task already running" | Only one task runs at a time. Cancel the current one first. |
| VM unreachable after reboot | Oracle may have changed the public IP on stop/start — update the IP in DuckDNS (Step 2). |
| "Out of capacity" creating the VM | Normal on free tier. Try another region / try again later. |
| Login page keeps appearing | Your session cookie expired (7 days) — log in again. |
| Chromium feels slow | It's a shared 4-core VM in another country — some lag is normal. Lowering `VNC_RESOLUTION` (e.g. `1024x640` in `.env`) helps on slow connections. |

Useful commands (in SSH):
```bash
cd /opt/browser-agent
docker compose ps                 # container status
docker compose logs -f            # all logs
docker compose logs -f agent      # just the agent
docker compose up -d --build      # rebuild after editing files
```

To update the site later: push changes to GitHub, then on the VM run
`sudo bash /tmp/setup.sh` again (it pulls the latest code and keeps your `.env`).

---

## Security notes

- Your site login is a single password (`SITE_PASSWORD`). Pick a long one.
  The live browser view (`/vnc/*`) is also gated behind that login.
- **Never put third-party passwords in `.env` or chat.** Log in manually through
  the browser (Step 7) — the agent reuses the saved session.
- Keep your Gemini key and site password private. `.env` is `chmod 600` and is not
  committed to git (add it to `.gitignore` if you fork this).
- This gives an AI agent control of a real logged-in browser: only give it tasks
  you trust it with, and watch it the first few times.

## Files

```
browser-agent/
├── docker-compose.yml   # 4 services: browser, agent, web, caddy
├── .env.example         # copy to .env (setup.sh does this)
├── setup.sh             # one-command installer for Ubuntu 24.04
├── README.md            # this file
├── browser/
│   ├── Dockerfile       # Xvfb + openbox + Chromium + x11vnc + noVNC (ARM-ready)
│   └── start.sh         # launches the display stack and headed Chromium w/ CDP
├── agent/
│   ├── Dockerfile
│   ├── requirements.txt # browser-use==0.13.11 (API-verified)
│   ├── main.py          # FastAPI: auth, task API, websocket, takeover/resume
│   ├── runner.py        # single-task browser-use runner + bot-check detection
│   └── llm_factory.py   # Gemini (free default) / OpenAI / Anthropic / BU gateway
├── web/
│   ├── Dockerfile       # nginx
│   ├── nginx.conf
│   ├── index.html       # mobile-first UI
│   ├── style.css
│   └── app.js
└── caddy/
    └── Caddyfile        # auto-HTTPS; /vnc/* behind login via forward_auth
```
