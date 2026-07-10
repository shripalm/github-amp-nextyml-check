import boto3
import json
import re
from urllib.request import urlopen

amplify = boto3.client("amplify")
sns = boto3.client("sns")

TOPIC_ARN = "arn:aws:sns:ap-south-1:XXXXXX:dev_notify"


def get_failure_reason(log: str):
    """Extract a concise reason from the Amplify build log."""

    if not log:
        return "Build log unavailable."

    # npm audit
    match = re.search(
        r'(\d+)\s+vulnerabilit(?:y|ies)\s+\(([^)]*)\)',
        log,
        re.IGNORECASE,
    )
    if match:
        return f"Security audit failed: {match.group(1)} vulnerabilities ({match.group(2)})."

    # Missing npm script
    match = re.search(r'Missing script:\s*"([^"]+)"', log)
    if match:
        return f'Missing npm script "{match.group(1)}".'

    # Next.js
    if "Failed to compile" in log:
        return "Next.js compilation failed."

    # TypeScript
    if "Type error:" in log:
        return "TypeScript compilation failed."

    # npm install
    if "npm ERR!" in log:
        return "Dependency installation failed."

    # Generic
    match = re.search(r'Command failed with exit code (\d+)', log)
    if match:
        return f"Command failed (exit code {match.group(1)})."

    return "Unknown build failure."


STATUS_CONFIG = {
    "SUCCEED": {
        "emoji": "✅",
        "label": "Succeeded",
        "subject_prefix": "SUCCESS",
        "summary_heading": "DEPLOYMENT SUMMARY",
        "footer": "The deployment completed successfully. No action is required.",
    },
    "FAILED": {
        "emoji": "❌",
        "label": "Failed",
        "subject_prefix": "FAILED",
        "summary_heading": "FAILURE SUMMARY",
        "footer": (
            "This build was automatically blocked by the CI/CD security gate.\n"
            "Please review the build log and resolve the issue before redeploying."
        ),
    },
    "CANCELLED": {
        "emoji": "⚠️",
        "label": "Cancelled",
        "subject_prefix": "CANCELLED",
        "summary_heading": "CANCELLATION SUMMARY",
        "footer": "The deployment was cancelled. Review if this was intentional.",
    },
}


def lambda_handler(event, context):

    print(json.dumps(event, indent=2))

    app_id = event["detail"]["appId"]
    branch = event["detail"]["branchName"]
    job_id = event["detail"]["jobId"]
    job_status = event["detail"]["jobStatus"]

    cfg = STATUS_CONFIG.get(job_status, {
        "emoji": "ℹ️",
        "label": job_status,
        "subject_prefix": job_status,
        "summary_heading": "DEPLOYMENT SUMMARY",
        "footer": "Review the deployment details.",
    })

    job = amplify.get_job(
        appId=app_id,
        branchName=branch,
        jobId=job_id,
    )

    summary = job["job"]["summary"]

    commit_id = summary.get("commitId")
    commit_message = summary.get("commitMessage")

    print("=" * 70)
    print(f"App      : {app_id}")
    print(f"Branch   : {branch}")
    print(f"Job ID   : {job_id}")
    print(f"Status   : {job_status}")
    print(f"Commit   : {commit_id}")
    print(f"Message  : {commit_message}")
    print("=" * 70)

    # --- Step-level inspection (log download only for FAILED) -----------

    build_log = ""
    failed_log_url = None

    for step in job["job"]["steps"]:

        print(f"\nStep   : {step['stepName']}")
        print(f"Status : {step['status']}")

        log_url = step.get("logUrl")

        if log_url:
            print(f"Log URL: {log_url}")

        if step["status"] == "FAILED" and log_url:

            failed_log_url = log_url

            try:
                with urlopen(log_url, timeout=30) as response:
                    build_log = response.read().decode("utf-8")

                print("\n========== BUILD LOG (first 1000 chars) ==========\n")
                print(build_log[:1000])
                print("\n==================================================\n")

            except Exception as ex:
                print(f"Unable to download log: {ex}")

    # --- Failure-specific analysis -------------------------------------

    reason = None
    packages = []

    if job_status == "FAILED":
        reason = get_failure_reason(build_log)
        packages = sorted(
            set(re.findall(r"node_modules/([^\s]+)", build_log))
        )

    # --- Console summary -----------------------------------------------

    print("\n")
    print("=" * 70)
    print(cfg["summary_heading"])
    print("=" * 70)
    print(f"Status: {cfg['emoji']} {cfg['label']}")

    if reason:
        print(f"Reason: {reason}")

    if packages:
        print("\nAffected Packages:")
        for package in packages:
            print(f"  • {package}")

    # --- Build email body ----------------------------------------------

    sections = [
        f"{cfg['emoji']} Amplify Build {cfg['label']}",
        "",
        "Application",
        "-----------",
        app_id,
        "",
        "Branch",
        "------",
        branch,
        "",
        "Job ID",
        "------",
        job_id,
        "",
        "Status",
        "------",
        f"{cfg['emoji']} {cfg['label']}",
        "",
        "Commit",
        "------",
        str(commit_id),
        "",
        "Commit Message",
        "--------------",
        str(commit_message),
    ]

    if reason:
        package_text = (
            "\n".join(f"- {pkg}" for pkg in packages) if packages else "None"
        )
        sections += [
            "",
            "Failure Reason",
            "--------------",
            reason,
            "",
            "Affected Packages",
            "-----------------",
            package_text,
        ]

    if failed_log_url:
        sections += [
            "",
            "Build Log",
            "---------",
            failed_log_url,
        ]

    sections += ["", cfg["footer"], ""]

    email_body = "\n".join(sections)

    sns.publish(
        TopicArn=TOPIC_ARN,
        Subject=f"[{cfg['subject_prefix']}] Amplify Build - {branch}",
        Message=email_body,
    )

    print("SNS notification sent successfully.")

    response_body = {
        "appId": app_id,
        "branch": branch,
        "jobId": job_id,
        "jobStatus": job_status,
        "commit": commit_id,
        "commitMessage": commit_message,
    }

    if reason:
        response_body["reason"] = reason
        response_body["packages"] = packages

    if failed_log_url:
        response_body["logUrl"] = failed_log_url

    return {
        "statusCode": 200,
        "body": response_body,
    }