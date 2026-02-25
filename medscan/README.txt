━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  MedScan — Deploy to Render.com (Free)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

STEP 1 — Push code to GitHub
──────────────────────────────
1. Go to https://github.com and create a free account
2. Click "New repository" → name it "medscan" → Create
3. In VS Code terminal run:

   git init
   git add .
   git commit -m "MedScan first deploy"
   git branch -M main
   git remote add origin https://github.com/YOUR_USERNAME/medscan.git
   git push -u origin main

STEP 2 — Deploy on Render.com
──────────────────────────────
1. Go to https://render.com → Sign up free (use GitHub login)
2. Click "New +" → "Web Service"
3. Connect your GitHub → select "medscan" repo
4. Fill in:
     Name        → medscan (or anything)
     Runtime     → Python 3
     Build Command  → pip install -r requirements.txt
     Start Command  → gunicorn app:app
5. Click "Advanced" → "Add Environment Variable"
   Add these 3 one by one:
     OCR_API_KEY      → your ocr.space key
     APPS_SCRIPT_URL  → your apps script URL
     SHEET_ID         → 1FgAbnK9wcDG1zRDYMjA5-Db_wZaQilNEaXaZh4wQNyM
6. Click "Create Web Service"
7. Wait ~2 minutes for it to build
8. You get a URL like: https://medscan.onrender.com ✅

STEP 3 — Done!
──────────────────────────────
Open your URL on any device, any browser, anywhere!
Share it with anyone who needs to use it.

NOTE: Free Render apps sleep after 15 mins of inactivity.
First load after sleep takes ~30 seconds to wake up.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
