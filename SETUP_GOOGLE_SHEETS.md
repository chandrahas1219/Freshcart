# FreshCart + Google Sheets Setup Guide

This version of FreshCart uses Google Sheets instead of local Excel files, so your data **persists forever** on Render (it doesn't disappear on app restart).

---

## **Step 1: Google Cloud Setup (one-time, 10 minutes)**

### 1.1: Create a Google Cloud Project
1. Go to **[console.cloud.google.com](https://console.cloud.google.com)**
2. Sign in with your Google account
3. Click **"Select a Project"** (top left) → **"New Project"**
4. Name it: `FreshCart`
5. Click **"Create"**
6. Wait 30 seconds for it to load

### 1.2: Enable Google Sheets API
1. Search for **"Google Sheets API"** in the search bar at the top
2. Click the result
3. Click **"Enable"**

### 1.3: Create a Service Account
1. Go to **"APIs & Services"** (left sidebar) → **"Credentials"**
2. Click **"Create Credentials"** (blue button) → **"Service Account"**
3. Fill in:
   - **Service account name:** `freshcart-app`
   - Leave the rest blank
4. Click **"Create and Continue"**
5. Skip the optional steps, click **"Done"**

### 1.4: Get the Service Account Key
1. Click on the service account email you just created
2. Go to the **"Keys"** tab
3. Click **"Add Key"** → **"Create new key"**
4. Choose **"JSON"**
5. A `.json` file downloads to your computer/phone

**IMPORTANT:** Save this file somewhere safe. You'll need it in Step 3.

### 1.5: Share Google Sheets with the Service Account
1. Open the downloaded JSON file (in a text editor)
2. Find the line that says: `"client_email": "freshcart-app@..."`
3. Copy the entire email address (e.g., `freshcart-app-1234@freshcart-123456.iam.gserviceaccount.com`)
4. Go to each of your 3 Google Sheets:
   - admins
   - customers
   - groceries
5. For each sheet, click **"Share"** → paste the email → select **"Editor"** → click **"Share"**

**Done with Google Cloud.** ✅

---

## **Step 2: Encode the JSON Key for Render**

Now you need to convert the JSON key to a format that Render can store.

### If you're on desktop:
```bash
# Mac/Linux:
base64 -i /path/to/downloaded/key.json | pbcopy

# Windows (PowerShell):
[Convert]::ToBase64String([System.IO.File]::ReadAllBytes("C:\path\to\key.json")) | Set-Clipboard
```

This copies the base64-encoded key to your clipboard.

### If you're on mobile:
1. Open the downloaded JSON file in a text editor
2. Copy all its content
3. Go to an online base64 encoder: **[base64encode.org](https://www.base64encode.org)**
4. Paste the JSON content
5. Click "Encode"
6. Copy the output (this is your encoded key)

---

## **Step 3: Deploy to Render**

### 3.1: Upload to GitHub
1. Go to **[github.com](https://github.com)**
2. Click **"New"** → Create a repository called `freshcart`
3. Click **"Add file"** → **"Upload files"**
4. Upload ALL files from the `freshcart-google-sheets/` folder:
   - `app.py`
   - `config.py`
   - `google_sheets_helpers.py`
   - `decorators.py`
   - `cart_utils.py`
   - `requirements.txt`
   - All folders: `routes/`, `templates/`, `static/`
5. Click **"Commit changes"**

### 3.2: Deploy to Render
1. Go to **[render.com](https://render.com)**
2. Sign up/log in with GitHub
3. Click **"New +"** → **"Web Service"**
4. Connect your `freshcart` GitHub repo
5. Fill in:
   - **Name:** `freshcart`
   - **Environment:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app`
   - **Plan:** Free
6. Scroll down to **"Environment"** section
7. Add these 3 environment variables (click **"Add Environment Variable"**):

   | Key | Value |
   |-----|-------|
   | `GOOGLE_SHEETS_CREDENTIALS` | Paste the base64-encoded JSON key from Step 2 |
   | `ADMIN_KEY` | `SECRET123` (or make up your own) |
   | `FLASK_SECRET_KEY` | `your-random-secret-key` (just type something long) |

8. Click **"Create Web Service"**
9. **Wait 2-3 minutes** while it builds and deploys

Your app is now live! 🎉

---

## **Step 4: Test the App**

1. You should see a URL like: `https://freshcart-xxxx.onrender.com`
2. Click it or open in your browser
3. Register an admin (use your ADMIN_KEY)
4. Add some groceries
5. Register a customer
6. Shop, add to cart, checkout
7. **Check your Google Sheets** — orders, customers, and stock updates should all be there!

---

## **Troubleshooting**

### "Failed to load Google Sheets credentials"
- Make sure you added the `GOOGLE_SHEETS_CREDENTIALS` environment variable in Render
- Make sure it's the full base64-encoded JSON (not just the email)
- Make sure it was pasted correctly (no line breaks)

### "Worksheet not found"
- Make sure you shared all 3 Google Sheets with the service account email
- Make sure the Sheet IDs in `google_sheets_helpers.py` match your sheets

### App won't start
- Check the build log in Render (it shows errors)
- Make sure `gunicorn` is in `requirements.txt`

---

## **Now you can use it!**

- **Admin portal:** `/admin/verify-key` → enter key → register
- **Customer portal:** `/customer/register` → shop
- **Data persists:** Everything saves to your Google Sheets

**Enjoy! 🛒**
