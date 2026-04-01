# Deployment Guide: Netlify + Railway

This guide walks you through deploying the Legal AI Platform with:
- **Frontend**: Netlify (static hosting with API proxy)
- **Backend**: Railway (FastAPI server)

---

## Prerequisites

1. **GitHub Account** - Your code must be in a GitHub repository
2. **Railway Account** - Sign up at https://railway.app (free tier available)
3. **Netlify Account** - Sign up at https://netlify.com (free tier available)
4. **Environment Variables Ready**:
   - `GROQ_API_KEY` - Your Groq API key
   - `SESSION_SECRET` - Any random string (e.g., generate with `openssl rand -hex 32`)

---

## Step 1: Push Code to GitHub

If your code isn't already on GitHub:

```bash
cd /Users/adityapatiyal/Desktop/Legal

# Initialize git if needed
git init

# Add all files
git add .

# Commit
git commit -m "Initial commit - Legal AI Platform"

# Create a new repo on GitHub, then:
git remote add origin https://github.com/YOUR-USERNAME/YOUR-REPO-NAME.git
git branch -M main
git push -u origin main
```

---

## Step 2: Deploy Backend on Railway

### 2.1 Create New Project
1. Go to https://railway.app
2. Click **"New Project"**
3. Select **"Deploy from GitHub repo"**
4. Authorize Railway to access your GitHub account
5. Select your Legal AI repository

### 2.2 Configure the Service
1. Railway will auto-detect it's a Python project
2. Click on your service → **Settings** tab

### 2.3 Set Start Command
- Go to **Settings** → **Deploy** section
- Set **Start Command**:
  ```
  uvicorn backend.app:app --host 0.0.0.0 --port $PORT
  ```

### 2.4 Add Environment Variables
- Go to **Variables** tab
- Add these variables:
  - `GROQ_API_KEY` = `your_groq_api_key_here`
  - `SESSION_SECRET` = `your_random_secret_here`
  - `PYTHONPATH` = `.` (optional, helps with imports)

### 2.5 Deploy
1. Click **Deploy** (or it may auto-deploy)
2. Wait for build to complete (check **Deployments** tab)
3. Once deployed, go to **Settings** → **Networking**
4. Click **Generate Domain** to get a public URL
5. **COPY THIS URL** - you'll need it for Netlify (e.g., `https://legal-backend-production.up.railway.app`)

### 2.6 Verify Backend is Running
Open your Railway URL in a browser and add `/api/me` to test:
- Example: `https://your-railway-app.up.railway.app/api/me`
- You should see a 401 error (expected - means the API is working)

---

## Step 3: Deploy Frontend on Netlify

### 3.1 Update netlify.toml
1. Open `netlify.toml` in your project root
2. Find this line:
   ```toml
   to = "https://YOUR-RAILWAY-APP.up.railway.app/api/:splat"
   ```
3. Replace `YOUR-RAILWAY-APP.up.railway.app` with your actual Railway domain
4. Save the file
5. Commit and push to GitHub:
   ```bash
   git add netlify.toml
   git commit -m "Update Railway URL in netlify.toml"
   git push
   ```

### 3.2 Create Netlify Site
1. Go to https://netlify.com
2. Click **"Add new site"** → **"Import an existing project"**
3. Choose **GitHub** and authorize Netlify
4. Select your Legal AI repository

### 3.3 Configure Build Settings
- **Build command**: Leave empty (no build needed)
- **Publish directory**: `.` (dot - means root)
- Click **"Deploy site"**

### 3.4 Get Your Netlify URL
1. After deployment completes, you'll see your site URL
2. It will be something like: `https://random-name-123.netlify.app`
3. **COPY THIS URL** - you need it for the next step

---

## Step 4: Update Railway CORS Settings

Your backend needs to allow requests from your Netlify domain.

### 4.1 Add CORS_ORIGINS Variable
1. Go back to Railway → your service → **Variables** tab
2. Add a new variable:
   - Key: `CORS_ORIGINS`
   - Value: `https://your-netlify-site.netlify.app` (use your actual Netlify URL)

### 4.2 Update Backend Code (if needed)
The backend currently has `allow_origins=["*"]` which works but is less secure. Optionally update it:

In `backend/app.py`, change:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Change this
    ...
)
```

To:
```python
import os

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    ...
)
```

Then commit and push - Railway will auto-redeploy.

---

## Step 5: Test Your Deployed Site

### 5.1 Open Your Netlify URL
Visit `https://your-netlify-site.netlify.app`

### 5.2 Test These Features
1. **Landing page loads** with the expandable ask bar
2. **Click the ask bar** - it should expand with suggestions
3. **Sign up** for a new account
4. **Verify auth section disappears** after login
5. **Go to /dashboard** - should load without redirect
6. **Ask a question** on the dashboard - should answer inline
7. **Upload a document** - should work (but remember: uploads are ephemeral on free tier)
8. **Go to /chat** - test document-based chat
9. **Go to /generator** - test document generation

### 5.3 Check Browser Console
- Open DevTools (F12)
- Check Console tab - should see no CORS errors
- Check Network tab - API calls to `/api/*` should succeed

---

## Important Notes

### ⚠️ Ephemeral Storage Warning
- **Uploads** (`storage/`) and **ChromaDB** (`chroma/`) are stored inside the Railway container
- They will be **cleared** when:
  - You redeploy the backend
  - Railway restarts the service
  - The service goes to sleep (on free tier)

### 💰 To Add Persistent Storage (Optional)
1. In Railway, go to your service
2. Click **"+ New"** → **"Volume"**
3. Mount path: `/data`
4. Add environment variables:
   - `CHROMA_DIR=/data/chroma`
   - `STORAGE_DIR=/data/storage`
5. Update `backend/database.py` to use these env vars instead of hardcoded paths

### 🔒 Security Best Practices
- Never commit `.env` file to GitHub
- Use Railway's environment variables for all secrets
- Consider updating CORS to use specific origins (not `*`)

### 🚀 Custom Domain (Optional)
- **Netlify**: Settings → Domain management → Add custom domain
- **Railway**: Settings → Networking → Custom domain
- Both provide free SSL certificates

---

## Troubleshooting

### Backend won't start
- Check Railway **Deployments** tab for build logs
- Verify `requirements.txt` is in `backend/` folder
- Ensure `PYTHONPATH=.` is set in Railway variables

### API calls fail with CORS errors
- Verify `CORS_ORIGINS` in Railway matches your Netlify URL exactly
- Check that `netlify.toml` has the correct Railway URL

### 401 errors on protected routes
- Check browser cookies - `session_token` should be set after login
- Verify Railway backend is receiving the cookie

### Uploads fail
- Normal on first deploy - storage folders are created automatically
- If persists, check Railway logs for permission errors

---

## Deployment Checklist

- [ ] Code pushed to GitHub
- [ ] Railway project created and deployed
- [ ] Railway environment variables set (GROQ_API_KEY, SESSION_SECRET)
- [ ] Railway public URL copied
- [ ] netlify.toml updated with Railway URL
- [ ] Netlify site created and deployed
- [ ] Netlify URL copied
- [ ] Railway CORS_ORIGINS updated with Netlify URL
- [ ] Site tested: signup, login, ask questions, upload docs
- [ ] No console errors in browser

---

## Next Steps After Deployment

1. **Monitor Usage**: Check Railway and Netlify dashboards for usage
2. **Add Persistence**: If you need uploads to survive redeploys, add a Railway Volume
3. **Custom Domain**: Add your own domain for a professional look
4. **Monitoring**: Set up error tracking (e.g., Sentry)
5. **Backups**: Regularly backup your database and important files

---

## Support

If you encounter issues:
1. Check Railway deployment logs
2. Check Netlify deploy logs
3. Check browser console for errors
4. Verify all environment variables are set correctly
