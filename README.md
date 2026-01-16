# Economics Research Digest

Automated weekly aggregator for economics working papers, filtered for progressive policy priorities.

## What It Does

Every Monday at 7am ET, this workflow:
1. Pulls new papers from 8 sources (VoxEU, Equitable Growth, EPI, Fed working papers, Brookings, SSRN)
2. Filters by 50+ keywords (corporate power, housing, labor, inequality, pricing, etc.)
3. Emails you a ranked digest with links

## Setup (10 minutes)

### 1. Create the GitHub repo

- Go to github.com → New Repository
- Name it `econ-research-digest` (or whatever)
- Make it private
- Upload these files:
  - `econ_research_digest.py`
  - `.github/workflows/weekly-digest.yml`

### 2. Create a Gmail App Password

You need an "app password" (not your regular Gmail password):

1. Go to myaccount.google.com → Security
2. Enable 2-Step Verification if not already on
3. Search for "App passwords" or go to: https://myaccount.google.com/apppasswords
4. Create new app password → name it "GitHub Digest"
5. Copy the 16-character password (looks like: `abcd efgh ijkl mnop`)

### 3. Add GitHub Secrets

In your GitHub repo:
1. Go to Settings → Secrets and variables → Actions
2. Add these secrets:

| Secret Name | Value |
|-------------|-------|
| `EMAIL_USERNAME` | your-email@gmail.com |
| `EMAIL_APP_PASSWORD` | the 16-char app password from step 2 |
| `EMAIL_TO` | where to send the digest (can be same as username) |

### 4. Test It

- Go to Actions tab in your repo
- Click "Weekly Economics Research Digest"
- Click "Run workflow" → "Run workflow"
- Wait ~1 minute, check your email

## Customization

### Change the schedule

Edit `.github/workflows/weekly-digest.yml`:
```yaml
schedule:
  - cron: '0 12 * * 1'  # Monday 7am ET (12:00 UTC)
```

Other examples:
- `'0 14 * * 1'` = Monday 9am ET
- `'0 12 * * 1,4'` = Monday and Thursday 7am ET
- `'0 12 * * *'` = Every day 7am ET

### Change keywords

Edit the `PRIORITY_KEYWORDS` list in `econ_research_digest.py` to add terms relevant to current projects.

### Add sources

Add RSS feeds to the `SOURCES` dict in the script. Most think tanks and Fed banks have RSS feeds.

## Sources Included

| Source | Focus |
|--------|-------|
| VoxEU/CEPR | Policy-relevant research summaries |
| Equitable Growth | Progressive econ, inequality |
| EPI | Labor, wages, inequality |
| Fed Board Working Papers | Macro, finance, labor |
| NY Fed Liberty Street | Accessible Fed research |
| SF Fed Economic Letters | West coast Fed analysis |
| Brookings Economics | Policy research |
| SSRN Economics | Preprints |
