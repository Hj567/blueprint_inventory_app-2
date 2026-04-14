# Blueprint Inventory Mapper

A Flask web app that:
- loads the hardcoded blueprint PDF and unsold inventory Excel file
- detects unit references like `LF-A-405` from the PDF
- matches them to the inventory sheet
- highlights the unsold units on the blueprint pages
- shows inventory details in a table
- lets users select units and totals the selected square footage
- saves each person's selection separately in Firebase Firestore
- shows a comparison table so multiple users can compare saved baskets

## Run locally

```bash
cd blueprint_inventory_app
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Then open:

```text
http://127.0.0.1:5001
```

## Firebase setup

Create a Firebase project and enable **Cloud Firestore**.

Set these environment variables before running the Flask app:

```bash
export FIREBASE_API_KEY="your_api_key"
export FIREBASE_AUTH_DOMAIN="your_project.firebaseapp.com"
export FIREBASE_PROJECT_ID="your_project_id"
export FIREBASE_STORAGE_BUCKET="your_project.firebasestorage.app"
export FIREBASE_MESSAGING_SENDER_ID="your_sender_id"
export FIREBASE_APP_ID="your_app_id"
```

Then restart the app.

The frontend reads these values from `/firebase-config.js` and writes selections into:

```text
blueprintSelections/{jobId}/userSelections/{userDocId}
```

Each record stores:
- display name
- internal user id
- selected unit codes
- selected unit count
- total selected area
- updated timestamp

## Suggested Firestore rules for internal use

Use stricter rules in production if you add authentication. For a fast internal rollout, you can begin with time-limited test mode or use a rule structure like this and later tighten it:

```text
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /blueprintSelections/{jobId}/userSelections/{docId} {
      allow read, write: if true;
    }
  }
}
```

## Expected Excel format
The first usable header row should contain columns similar to:
- S.NO.
- LEVEL (SPR Ref.)
- FLOOR
- TYPE
- SHOP NO
- UDS (Sq. ft.)
- TOTAL AREA (Sq.ft)

The parser tries to detect the header row automatically.

## Notes
- The app highlights the location of the unit label found in the PDF. In most blueprint PDFs this is good enough to show where the unit sits on the plan.
- Units found in Excel but not detected in the PDF remain visible in the table and are marked without a page.
- This version is hardcoded to the uploaded PDF and Excel file.
- Shared selections require internet access because Firebase is loaded in the browser.
