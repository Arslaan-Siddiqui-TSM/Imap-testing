# **IMAP OAuth2 Testing Toolkit**

A small toolkit and Streamlit demo application for authenticating to **Gmail** and **Outlook** via **OAuth2 (XOAUTH2)** and running basic IMAP operations using an asynchronous client.

This project is intended as a clear, minimal reference for:

* acquiring tokens interactively (Google & Microsoft),
* refreshing tokens,
* discovering the authenticated email account,
* connecting to IMAP using XOAUTH2,
* testing IMAP access programmatically or via a UI.

---

# **Table of Contents**

1. [Features](#features)
2. [Project Structure](#project-structure)
3. [Prerequisites](#prerequisites)
4. [Quick Start](#quick-start)
5. [.env Setup](#env-setup)
6. [Generating OAuth Tokens](#generating-oauth-tokens)
7. [Gmail Setup (Google Cloud Console)](#gmail-setup-google-cloud-console)
8. [Outlook Setup (Azure Portal)](#outlook-setup-azure-portal)
9. [Running the Tools](#running-the-tools)
10. [Behavior Notes](#behavior-notes)
11. [Scopes & Permissions Reference](#scopes--permissions-reference)
12. [Troubleshooting](#troubleshooting)
13. [Security Notes](#security-notes)

---

# **Features**

* OAuth2 helper scripts for **Gmail** and **Outlook**
* Interactive token generation (desktop installed-app flow / MSAL public client)
* Token refresh helpers
* Automatic email discovery using Google/Gmail APIs and Microsoft Graph/ID token claims
* Asynchronous IMAP client for testing XOAUTH2 authentication
* Streamlit UI for quick validation of IMAP connectivity

---

# **Project Structure**

```
src/
  gmail_oauth.py        # Interactive Google OAuth helper
  outlook_oauth.py      # Interactive Microsoft OAuth helper
  token_utils.py        # Token refresh and email discovery
  imap_client.py        # Async IMAP XOAUTH2 client (AsyncIMAPClient)

app.py                  # Streamlit testing UI
test_run.py             # Async test runner (parallel connect + fetch)
```

---

# **Prerequisites**

* **Python 3.10+**
* OAuth applications registered in:

  * **Google Cloud Console** (for Gmail)
  * **Azure Portal** (for Outlook / Microsoft 365 / Outlook.com)
* A `.env` file containing OAuth credentials
  (see next section; **never commit this file**)

This project works on **Windows**, **macOS**, and **Linux**. Commands below use Windows examples where relevant.

---

# **Quick Start**

### **1. Create and activate a virtual environment**

**Windows (PowerShell)**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

**macOS / Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### **2. Install dependencies**

```bash
pip install -r requirements.txt
```

### **3. Create your `.env` file**

See the template below.

### **4. Generate tokens**

```bash
python -m src.gmail_oauth
python -m src.outlook_oauth
```

### **5. Test IMAP**

```bash
python test_run.py
```

### **6. Run the Streamlit UI**

```bash
streamlit run app.py
```

---

# **.env Setup**

Create a `.env` file at the project root:

```env
# Gmail OAuth
GMAIL_CLIENT_ID=your-google-client-id
GMAIL_CLIENT_SECRET=your-google-client-secret
GMAIL_ACCESS_TOKEN=
GMAIL_REFRESH_TOKEN=

# Outlook OAuth (MSAL public client)
OUTLOOK_CLIENT_ID=your-azure-client-id
OUTLOOK_TENANT_ID=common
OUTLOOK_ACCESS_TOKEN=
OUTLOOK_REFRESH_TOKEN=
```

Tokens will be filled automatically after running the OAuth scripts.

---

# **Generating OAuth Tokens**

### **Fast method (recommended)**

From the project root:

```bash
python -m src.gmail_oauth
python -m src.outlook_oauth
```

Each script:

* opens a browser,
* walks you through OAuth sign-in,
* outputs access + refresh tokens,
* outputs discovered email (if available).

Copy the values into your `.env`.

---

# **Gmail Setup (Google Cloud Console)**

<details>
<summary><strong>Click to expand detailed steps</strong></summary>

### **1. Create or select a project**

[https://console.cloud.google.com](https://console.cloud.google.com)

### **2. Enable the Gmail API**

`APIs & Services → Library → Gmail API → Enable`

### **3. Configure the OAuth consent screen**

* Type: **External** (recommended for testing)
* Fill App name & emails
* Add scope:
  `https://mail.google.com/`
* Keep Publishing status = **Testing**
* Add your Google accounts under **Test users**

### **4. Create OAuth credentials**

`Credentials → Create Credentials → OAuth client ID`

* Application type: **Desktop app**
* Copy **Client ID** and **Client Secret** into your `.env`

### **5. Generate tokens**

```bash
python -m src.gmail_oauth
```

</details>

---

# **Outlook Setup (Azure Portal)**

<details>
<summary><strong>Click to expand detailed steps</strong></summary>

### **1. Register an app**

Azure Portal → Azure Active Directory → App registrations → *New registration*

* Supported account types:
  **“Personal + Work/School accounts”**
* Redirect URI: not required for MSAL interactive desktop flow

### **2. Record app identifiers**

Use in `.env`:

* **Application (client) ID → OUTLOOK_CLIENT_ID**
* **Directory (tenant) ID → OUTLOOK_TENANT_ID** (or use `common`)

### **3. Authentication settings**

* Add **Mobile and desktop applications**
* Enable **Allow public client flows**

### **4. API permissions**

Add:

* `IMAP.AccessAsUser.All` (Exchange Online delegated)
  **or**
* Graph delegated permissions:

  * `Mail.Read` / `Mail.ReadWrite`
* Always add:

  * `offline_access`
  * `openid`, `profile`, `email`

Admin consent may be required.

### **5. Generate tokens**

```bash
python -m src.outlook_oauth
```

</details>

---

# **Running the Tools**

### **Generate tokens**

```bash
python -m src.gmail_oauth
python -m src.outlook_oauth
```

### **Run the async IMAP test**

```bash
python test_run.py
```

### **Run the Streamlit UI**

```bash
streamlit run app.py
```

---

# **Behavior Notes**

* **Automatic email discovery**

  * Gmail: via `users/me/profile`
  * Microsoft: via ID token claims or Graph `/me`

* **Token refresh**

  * Helpers detect expired access tokens and exchange refresh tokens for new ones
  * If a new refresh token is issued, `.env` is updated automatically

* **IMAP client**

  * Uses OAuth2 XOAUTH2 only
  * No password fallback is supported

---

# **Scopes & Permissions Reference**

## **Gmail**

### IMAP scope

* `https://mail.google.com/`

### Optional identity

* `openid`
* `email`
* `profile`

### Recommended

```
["https://mail.google.com/", "openid", "email", "profile"]
```

---

## **Microsoft / Outlook**

### IMAP delegated

* `IMAP.AccessAsUser.All`

### Graph mail

* `Mail.Read`
* `Mail.ReadWrite`

### Identity & refresh

* `offline_access`
* `openid`
* `profile`
* `email`

### Recommended sets

**Graph (read-only):**

```
["offline_access", "openid", "profile", "Mail.Read"]
```

**Graph (read-write):**

```
["offline_access", "openid", "profile", "Mail.ReadWrite"]
```

**IMAP:**

```
["offline_access", "openid", "profile", "IMAP.AccessAsUser.All"]
```

---

# **Troubleshooting**

### **Gmail 403 / access_denied**

* Ensure OAuth consent screen is configured
* Add signing account as a **Test user**
* Ensure Gmail API is enabled

### **Microsoft admin consent errors**

* Many tenants require admin approval for IMAP
* Try a personal account or a tenant where you have admin rights

### **ModuleNotFoundError: No module named 'src'**

Run scripts as modules from the project root:

```bash
python -m src.gmail_oauth
```

---

# **Security Notes**

* **Never commit `.env`**
* Use the **least-privileged scopes**
* Store refresh tokens in a secure secret store
* Public-client OAuth flows are fine for local testing; use **confidential clients** for production deployments

---
