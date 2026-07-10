# 🔒 Amplify Next.js — Secure CI/CD Pipeline

A **security-first CI/CD pipeline** for deploying Next.js applications on **AWS Amplify**, with automated vulnerability scanning, secret detection, and real-time deployment notifications via SNS.

---

## Architecture

```
Push to main
    │
    ├──► GitHub Actions CI          ──► lint → audit → gitleaks → semgrep → build
    │
    └──► AWS Amplify (cloudbuild)   ──► lint → audit → gitleaks → semgrep → build → deploy
                │
                ▼
         EventBridge Rule
         (SUCCEEDED / FAILED / CANCELLED)
                │
                ▼
         Lambda Function
                │
                ▼
         SNS Notification (Email)
```

---

## Security Gates

Every build runs through **four security checks** before the application is compiled:

| #  | Tool                                          | Purpose                          | Fails on                        |
|----|-----------------------------------------------|----------------------------------|---------------------------------|
| 1  | **ESLint**                                    | Code quality & best practices    | Lint errors                     |
| 2  | **npm audit**                                 | Dependency vulnerability scan    | High / critical vulnerabilities |
| 3  | [Gitleaks](https://github.com/gitleaks/gitleaks) | Secret & credential detection | Hardcoded secrets in git history |
| 4  | [Semgrep](https://semgrep.dev/)               | Static analysis (SAST)           | Security anti-patterns in code  |

---

## Pipelines

### GitHub Actions (`.github/workflows/ci.yml`)

Runs on every push to `main`. Uses official GitHub Actions for Gitleaks and Semgrep.

```
checkout → setup node 20 → npm install → lint → audit → gitleaks → semgrep → build → upload artifacts
```

### AWS Amplify (`cloudbuild.yml`)

Amplify's native build spec. Installs Gitleaks and Semgrep at build time since the Amplify environment runs Amazon Linux 2.

> **Note:** Semgrep is pinned to `v1.67.0` with `SEMGREP_FORCE_PYSEMGREP=true` to work around a glibc 2.35 incompatibility in the Amplify build image.

---

## Deployment Notifications (Lambda)

An **EventBridge rule** captures Amplify deployment status changes and triggers a Lambda function (`lambda-code.py`) that sends structured email notifications via **Amazon SNS**.

### Supported statuses

| Status        | Subject prefix   | Behavior                                                       |
|---------------|------------------|----------------------------------------------------------------|
| ✅ `SUCCEEDED` | `[SUCCESS]`      | Sends a confirmation email — no action required.              |
| ❌ `FAILED`    | `[FAILED]`       | Downloads the build log, extracts the failure reason and affected packages, and includes a link to the log. |
| ⚠️ `CANCELLED` | `[CANCELLED]`    | Sends a notification to review whether the cancellation was intentional. |

### Failure analysis

For failed builds, the Lambda automatically identifies:

- **npm audit failures** — vulnerability count and severity
- **Missing npm scripts** — exact script name
- **Next.js compilation errors**
- **TypeScript type errors**
- **Dependency installation failures**
- **Generic exit codes**
- **Affected packages** — extracted from the build log

### EventBridge rule

```json
{
  "source": ["aws.amplify"],
  "detail-type": ["Amplify Deployment Status Change"],
  "detail": {
    "jobStatus": ["FAILED", "SUCCEEDED", "CANCELLED"]
  }
}
```

### AWS resources required

| Resource          | Details                                                  |
|-------------------|----------------------------------------------------------|
| **Lambda**        | Python 3.10+ runtime, `lambda-code.py`                  |
| **EventBridge**   | Rule matching Amplify status changes (see above)         |
| **SNS Topic**     | `hfi_dev_notify` (or update `TOPIC_ARN` in the Lambda)   |
| **IAM**           | Lambda needs `amplify:GetJob`, `sns:Publish` permissions |

---

## Project Structure

```
.
├── .github/
│   └── workflows/
│       └── ci.yml              # GitHub Actions pipeline
├── src/
│   └── app/
│       ├── favicon.ico
│       ├── globals.css
│       ├── layout.js           # Root layout (Next.js App Router)
│       └── page.js             # Home page
├── cloudbuild.yml              # AWS Amplify build spec
├── lambda-code.py              # EventBridge → SNS notification Lambda
├── next.config.mjs             # Next.js configuration
├── eslint.config.mjs           # ESLint flat config
├── package.json
└── README.md
```

---

## Tech Stack

| Layer         | Technology                          |
|---------------|-------------------------------------|
| Framework     | Next.js 16 (App Router)            |
| Language      | JavaScript (React 19)              |
| Styling       | Tailwind CSS 4                     |
| Hosting       | AWS Amplify                        |
| CI            | GitHub Actions + Amplify Build     |
| Notifications | EventBridge → Lambda → SNS         |
| Security      | ESLint, npm audit, Gitleaks, Semgrep|

---

## Getting Started

### Prerequisites

- Node.js ≥ 20
- npm

### Local development

```bash
# Install dependencies
npm install

# Start dev server
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

### Available scripts

| Script            | Description                           |
|-------------------|---------------------------------------|
| `npm run dev`     | Start development server              |
| `npm run build`   | Production build                      |
| `npm run start`   | Serve production build                |
| `npm run lint`    | Run ESLint                            |

---

## Author

**Shripal Mehta**

## License

MIT