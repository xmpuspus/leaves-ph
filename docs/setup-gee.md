# Google Earth Engine setup

Leaves.PH pulls Sentinel-2 + Hansen + ESA + Dynamic World + AlphaEarth from Google Earth Engine. You need a free GEE account and a service-account key (for non-interactive runs) or an interactive auth (for development).

## One-time interactive auth (development)

```bash
pip install -r requirements.txt
earthengine authenticate
```

This opens a browser flow. Follow the prompts and paste the resulting token. The token lands at `~/.config/earthengine/credentials` and persists.

## Service-account auth (for batch runs)

1. Create a Google Cloud project: https://console.cloud.google.com/projectcreate
2. Enable the Earth Engine API for that project: https://console.cloud.google.com/apis/library/earthengine.googleapis.com
3. Register the project for Earth Engine: https://code.earthengine.google.com/register
4. Create a service account with the role "Earth Engine Resource Viewer".
5. Download the JSON key. Save it as `.ee-key.json` in the repo root (this filename is in `.gitignore`).

Then in code:

```python
import ee
import json

key_path = ".ee-key.json"
with open(key_path) as f:
    key = json.load(f)
credentials = ee.ServiceAccountCredentials(key["client_email"], key_path)
ee.Initialize(credentials)
```

## Quotas

GEE free tier is roughly 25 concurrent task slots, 250 export tasks per day, 10 GB storage. The full Leaves.PH NCR pull (Sentinel-2 + Hansen + ESA + Dynamic World + Meta) fits well within these limits; expect a one-time ~30 min run for the full 2016-2026 stack.

## Troubleshooting

- "Earth Engine API not enabled": revisit step 2.
- "Project not registered with Earth Engine": revisit step 3.
- "Permission denied for asset": some assets (e.g. AlphaEarth Foundations) require explicit opt-in. Visit the GEE catalog page and click "Sign up for access".
- "Export task quota exceeded": wait for the daily reset (00:00 PT) or distribute tasks across multiple service accounts.
