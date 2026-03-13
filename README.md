# LabSignal

> **Talk to your experimental data. Close the scientific loop.**

LabSignal is a live voice agent for research scientists and solo biotech founders working on cloud laboratory platforms. It listens to your questions about assay results, pulls data from three layers of your lab infrastructure in real time, and delivers variability-annotated verdicts — telling you not just what a result says, but whether you can trust it.

Built for the **Google Gemini Live Agent Challenge** using Google Agent Development Kit (ADK), Vertex AI Agent Engine, and Firestore.

---

## The Problem

Hormone and biomarker assay results are routinely misinterpreted — not because scientists are careless, but because the factors that distort results are scattered across systems that never talk to each other:

- **Patient records** hold medication lists (PPIs raise Chromogranin A by ~55%)
- **Sample handling logs** record freeze-thaw cycles (+23% CgA per cycle) and centrifugation delays
- **Instrument QC history** tracks CV drift and Westgard rule violations

A solo founder running experiments on a cloud lab platform like Emerald Cloud Lab has no senior scientist on call at midnight to synthesize all three. LabSignal is that scientist.

---

## Demo Scenario

> *"I just got a CgA result for patient P4471 at 310 ng/mL on instrument ELISA-01, sample S-2024-0391. Should I be concerned?"*

LabSignal:
1. Queries Firestore — finds patient P4471 is on **pantoprazole 40mg daily** (PPI, expected +55% CgA elevation)
2. Checks sample S-2024-0391 — **4h delay to centrifugation** + **1 freeze-thaw cycle** (+23%)
3. Reviews ELISA-01 QC history — **CV trending at 12.9%** (above 10% threshold), Westgard 1-2s warning
4. Synthesizes into a **CRITICAL risk verdict**: result is likely a gross overestimation, adjusted true value ~85 ng/mL (normal range)
5. Cites PubMed literature for every adjustment applied

The agent also reads uploaded images — Levey-Jennings charts, plate reader outputs, and standard curves — and interprets them with domain-specific scientific analysis.

---

## Architecture

```
Scientist (voice / text / image upload)
          │
          ▼
┌─────────────────────────────────────────┐
│         Gemini Live API                 │
│    (gemini-2.0-flash-live-001)          │
│    Real-time voice + interruption       │
└──────────────────┬──────────────────────┘
                   │ ADK tool calls
        ┌──────────┼──────────┐
        ▼          ▼          ▼
┌─────────────┐ ┌──────────────┐ ┌─────────────────────┐
│  Patient    │ │   Sample     │ │    Instrument       │
│ Confounders │ │ Chain Risk   │ │    QC History       │
│             │ │              │ │                     │
│ PPI use     │ │ Matrix       │ │ CV trend analysis   │
│ Renal fn    │ │ Freeze-thaw  │ │ Westgard violations │
│ Medications │ │ Temp excursion│ │ Lot change tracking │
└──────┬──────┘ └──────┬───────┘ └──────────┬──────────┘
       └───────────────┼──────────────────────┘
                       ▼
              ┌─────────────────┐
              │    Firestore    │
              │  (us-central1)  │
              │ patients/       │
              │ samples/        │
              │ instruments/    │
              └─────────────────┘
                       │
                       ▼
        ┌──────────────────────────┐
        │  Google Search grounding  │
        │  (PubMed / literature)    │
        └──────────────────────────┘
                       │
                       ▼
        Variability-annotated verdict
        Risk score + citations + recommended action
```

**GCP Services used:**
- Vertex AI Agent Engine (agent runtime)
- Cloud Run (backend serving)
- Firestore (patient, sample, instrument data)
- Cloud Build (CI/CD pipeline)
- Cloud Storage (staging artifacts, logs)
- BigQuery (telemetry)
- Secret Manager (GitHub PAT)

---

## Quickstart

### Prerequisites

- Python 3.10–3.13
- [uv](https://github.com/astral-sh/uv)
- [gcloud CLI](https://cloud.google.com/sdk/docs/install)
- [Terraform](https://developer.hashicorp.com/terraform/install) >= 1.14
- A GCP project with billing enabled

### 1. Clone and install

```bash
git clone https://github.com/ClustermyComputer/labsignal.git
cd labsignal
make install
```

### 2. Authenticate with GCP

```bash
gcloud auth login
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID
```

### 3. Enable required APIs

```bash
gcloud services enable \
  aiplatform.googleapis.com \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  firestore.googleapis.com \
  storage.googleapis.com \
  secretmanager.googleapis.com
```

### 4. Create Firestore database

```bash
gcloud firestore databases create --location=us-central1
```

### 5. Seed demo data

```bash
python seed_firestore.py
```

This creates three collections:
- `patients` — P4471 (PPI user), P1192 (active NET, PPI), P8834 (renal impairment, no PPI)
- `samples` — S-2024-0391 (delayed centrifugation), S-2024-0392 (plasma), S-2024-0393 (multiple freeze-thaw)
- `instruments` — ELISA-01 (CV drift, Westgard warnings), ELISA-02 (in control)

### 6. Run locally

```bash
make playground
```

Open `http://127.0.0.1:8501` and select the **app** agent.

---

## Deploy to GCP (Terraform)

### Configure variables

```bash
cp deployment/terraform/vars/env.tfvars.example deployment/terraform/vars/env.tfvars
```

Edit `env.tfvars`:
```hcl
project_name           = "labsignal"
prod_project_id        = "YOUR_PROJECT_ID"
staging_project_id     = "YOUR_PROJECT_ID"
cicd_runner_project_id = "YOUR_PROJECT_ID"
host_connection_name   = "git-labsignal"
github_pat_secret_id   = "github-pat-labsignal"
repository_owner       = "YOUR_GITHUB_USERNAME"
repository_name        = "labsignal"
region                 = "us-central1"
```

### Store your GitHub PAT in Secret Manager

```bash
echo -n "YOUR_GITHUB_TOKEN" | gcloud secrets create github-pat-labsignal \
  --data-file=- \
  --replication-policy=user-managed \
  --locations=us-central1
```

### Deploy

```bash
cd deployment/terraform
terraform init
terraform apply -var-file=vars/env.tfvars
```

Terraform provisions Agent Engine, Cloud Run, Cloud Build CI/CD pipelines, BigQuery telemetry, and all IAM bindings.

---

## Run Tests

```bash
# Unit tests (mocked Firestore — no GCP needed)
make test

# Or directly
uv run pytest tests/unit/ -v
```

12 unit tests covering:
- PPI confounder detection
- Sample chain risk scoring (plasma matrix, freeze-thaw, temp excursion)
- Instrument CV trend analysis and Westgard violation detection
- Graceful handling of unknown patient/sample/instrument IDs

---

## Domain Knowledge

LabSignal's variability scoring is grounded in published literature:

| Factor | Adjustment | Source |
|--------|-----------|--------|
| PPI use (any) | +55% CgA elevation | Giusti et al., ECL cell hyperplasia mechanism |
| Single freeze-thaw cycle | +23% CgA elevation | Pre-analytical stability studies |
| Plasma vs serum matrix | +30–40% higher in plasma | Matrix comparison studies |
| Between-kit variability (CgA) | Up to 6-fold difference | Cisbio vs KRYPTOR comparison |
| Between-lab bias (same kit) | -24% to +22.7% | Inter-laboratory comparison studies |

No FDA-approved CgA assay exists. LabSignal is designed to make this known variability explicit and actionable.

---

## Project Structure

```
labsignal/
├── app/
│   └── agent.py          # ADK agent — system prompt + 3 tool functions
├── tests/
│   ├── unit/
│   │   └── test_labsignal_tools.py   # 12 unit tests (mocked Firestore)
│   ├── integration/
│   │   └── test_agent.py             # Integration test via ADK runner
│   └── eval/                         # Eval sets for agent quality
├── deployment/
│   └── terraform/        # Full IaC — Agent Engine, Cloud Run, Cloud Build
├── seed_firestore.py      # One-time data seeding script
└── Makefile               # install / playground / test / deploy
```

---

## Roadmap

- **Voice loop** — Gemini Live API integration (`gemini-2.0-flash-live-001`) pending Vertex AI access in project
- **Real LIS integration** — HL7/FHIR feed replacing mock Firestore fixtures
- **Expanded assay coverage** — AMH, estradiol, testosterone variability profiles
- **Multi-patient dashboard** — batch risk scoring across a run

---

## Built With

- [Google Agent Development Kit (ADK)](https://google.github.io/adk-docs/)
- [Agent Starter Pack](https://github.com/GoogleCloudPlatform/agent-starter-pack)
- [Vertex AI Agent Engine](https://cloud.google.com/vertex-ai/docs/agent-engine)
- [Firestore](https://cloud.google.com/firestore)
- [Gemini 2.0](https://deepmind.google/technologies/gemini/)

---

## License

Apache 2.0 — see [LICENSE](LICENSE)
