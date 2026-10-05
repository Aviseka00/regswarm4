# RegSwarm — live evidence analysis

RegSwarm analyzes imported inspection observations and versioned site evidence using Anthropic or Groq. Scripted responses, synthetic case selection, demonstration pacing, and seeded citation errors are unavailable in the application.

## Local setup

1. Load the regulatory corpus: `python ingest/fetch_ecfr.py`.
2. Create an account: `python manage.py create-user --username YOUR_USERNAME --name "Your Full Name"`. Passwords are entered interactively and stored as salted PBKDF2 hashes. Add `--role analyst` for users who must not approve responses.
3. Configure a live provider. Anthropic requires `ANTHROPIC_API_KEY` and `REGSWARM_MODEL` with a supported model name. Groq uses `GROQ_API_KEY` and optional `REGSWARM_GROQ_MODEL`; its current default is `qwen/qwen3.8-27b`. Windows-encrypted local provider credentials are also supported and excluded from version control. No key is sent to the browser.
4. Start `python server.py` or `run.bat`. Open http://127.0.0.1:8791/ and sign in.
5. Import a JSON evidence package following `case-package-template.json`. Replace every empty field with actual source information. Supply only evidence you are authorized to send to the selected provider. Check the provider transmission acknowledgement and choose **Analyze case**.
6. Inspect source passages, citations, and missing evidence in **Evidence review**. A reviewer must confirm every interpretation and critique finding, record a review comment, and acknowledge the commitments before approval.

The first account has not been created automatically. Real evidence is not shipped with the app. Old synthetic files remain solely for offline regression tests and are inaccessible through production case/history APIs.

## Case import contract

A case has `title`, `observation`, `site_name`, `product_class`, `authority: "US FDA"`, `synthetic: false`, and `documents`. Each document needs a unique `id`, `title`, `version`, ISO `date`, `status`, `group`, `source`, and nonempty `sections` with `ref` and `text`. Import stores hashes and source versions. The importer validates structure and provenance fields; it cannot independently certify that an upload is authentic. Attach complete relevant passages, not model-generated summaries.

The current regulatory corpus verifies 21 CFR citations. EMA, MHRA, and CDSCO processing is blocked until their sources and verifiers are implemented. The live workflow no longer injects the former environmental-monitoring dataset, synthetic risk matrix, or fixed root causes. Broader analytics require validated data-specific calculation modules.

## Implemented controls

- Local account authentication; reviewer/analyst roles; eight-hour HttpOnly, SameSite sessions; throttled sign-in attempts.
- Same-origin and CSRF checks; host validation; bounded JSON imports; security response headers; loopback-only binding.
- Two concurrent workflow limit; durable case packages and per-model-call run checkpoints; interrupted jobs fail closed after restart.
- Strict JSON parsing and structural checks; case-scoped evidence/clause references; finite provider timeout; bounded retries for transient HTTP failures; incomplete outputs rejected.
- Human interpretation review; authenticated decision attribution; document-version hash checking; export integrity checks; hash-chained audit entries.
- Empty responses, blocked claims, evidence gaps, and failed citation currency checks cannot be approved.
- No automatic regulatory submission. No browser-exposed provider keys. Credentials encrypted using Windows DPAPI belong to the provisioning Windows account; run the service as that account.

## Deployment limits

This is a hardened local application, not a validated regulated production deployment. The bundled standard-library HTTP service intentionally cannot bind publicly. A multiuser deployment still needs an approved application server and TLS/identity boundary, tenant isolation, infrastructure secrets management, encrypted evidence storage, tested backups and disaster recovery, monitoring, load/security testing, and a formal validation package with expert-reviewed cases. The audit hash chain is not externally anchored. Local passwords are not SSO/MFA, and approval attribution does not by itself establish electronic-signature compliance. Do not claim Part 11/GAMP validation from these controls alone.

Run one service process per database; startup recovery marks unfinished runs interrupted. A new run is required after interruption. Completed runs remain available in History. Session state is intentionally invalidated on restart.

## Verification

`python -m unittest discover -s tests -v`

Tests use isolated temporary databases, provider doubles, and synthetic fixtures. They do not populate the application's case store or send site data to external providers. Live provider connection checks are separate from end-to-end regulatory validation.


## Facility libraries
Open `/facilities` after signing in. Provision a dedicated administrator with `python manage.py create-user --username admin --name "Administrator" --role admin`. Existing reviewer accounts retain their role; admin manages facilities and libraries, reviewer approves responses.

Administrators can create Facility 01, 02 and further facilities (or supply names), add custom categories, and store immutable document versions. Default categories: SOP, STP, Protocol, BMR, Deviation, CAPA, Change control, Risk assessment. Upload UTF-8 TXT/MD/CSV, DOCX or passage JSON (up to 3 MB). PDF/scanned files require a verified text export; automatic OCR is not implemented. Verify source content and metadata before analysis.

Facility search uses persistent SQLite FTS5 BM25 indexes and up to eight concurrent category search workers. Custom categories receive the same search worker behavior. Queries remain local. Search results include record/version/passage identifiers and hashes. Create a case from selected document versions to use the live analysis workspace. Cases retain source snapshots and facility IDs; later uploads cannot change prior cases. Select only one version per document. Facility separation scopes libraries/search/case selection; all authenticated users share this local application's facilities (no per-facility access control). No benchmark claim is made about speed improvements.
