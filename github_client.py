"""GitHub API client for workflow logs, issues, and fix pull requests."""

from __future__ import annotations

import base64
import io
import re
import zipfile
from datetime import datetime, timezone
from typing import Any

import requests

GITHUB_API_VERSION = "2022-11-28"


class GitHubAPIError(Exception):
    """Raised when a GitHub API request fails with a user-friendly message."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _github_headers(token: str) -> dict[str, str]:
    """Build standard GitHub REST API headers."""
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
    }


def _normalize_job_name(name: str) -> str:
    """Normalize a job name for matching zip archive folder names."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _raise_github_error(response: requests.Response, action: str) -> None:
    """Raise GitHubAPIError with a helpful message based on status code."""
    status = response.status_code
    if status == 403:
        raise GitHubAPIError(
            f"{action} failed (403): token missing required scopes. "
            "Use a classic PAT with `repo` and `workflow`, or fine-grained PAT with Actions: Read.",
            status,
        )
    if status == 404:
        raise GitHubAPIError(
            f"{action} failed (404): run not found or logs expired. "
            "Verify owner, repo, and run ID from the Actions run URL.",
            status,
        )
    if status in {202, 409}:
        raise GitHubAPIError(
            f"{action} failed ({status}): workflow run still in progress. "
            "Wait for the run to finish before fetching logs.",
            status,
        )
    raise GitHubAPIError(f"{action} failed ({status}): {response.text[:300]}", status)


def validate_run_id(run_id: str) -> int:
    """Validate and return run ID as an integer."""
    cleaned = run_id.strip()
    if not cleaned.isdigit():
        raise GitHubAPIError("Run ID must be numeric. Find it in the Actions run URL: /actions/runs/123456789")
    return int(cleaned)


def _download_log_archive(url: str, token: str) -> bytes:
    """Download workflow log zip archive using redirect-safe requests."""
    first = requests.get(
        url,
        headers=_github_headers(token),
        allow_redirects=False,
        timeout=120,
    )
    if first.status_code in {301, 302, 303, 307, 308}:
        download_url = first.headers.get("Location")
        if not download_url:
            raise GitHubAPIError("GitHub log download redirect missing Location header.")
        second = requests.get(download_url, timeout=120)
        if second.status_code >= 400:
            _raise_github_error(second, "Log archive download")
        content = second.content
    else:
        if first.status_code >= 400:
            _raise_github_error(first, "Log archive request")
        content = first.content

    if content[:1] in {b"{", b"["}:
        raise GitHubAPIError(
            "GitHub returned an error response instead of a log archive. "
            "Check token scopes and that the run has completed."
        )
    return content


def fetch_workflow_run(owner: str, repo: str, run_id: str | int, token: str) -> dict[str, Any]:
    """Fetch workflow run metadata."""
    url = f"https://api.github.com/repos/{owner}/{repo}/actions/runs/{run_id}"
    response = requests.get(url, headers=_github_headers(token), timeout=60)
    if response.status_code >= 400:
        _raise_github_error(response, "Workflow run lookup")
    data = response.json()
    return {
        "id": data.get("id"),
        "name": data.get("name"),
        "status": data.get("status"),
        "conclusion": data.get("conclusion"),
        "workflow_path": data.get("path"),
        "html_url": data.get("html_url"),
        "head_branch": data.get("head_branch"),
    }


def fetch_workflow_jobs(owner: str, repo: str, run_id: str | int, token: str) -> list[dict[str, Any]]:
    """Fetch jobs for a workflow run."""
    url = f"https://api.github.com/repos/{owner}/{repo}/actions/runs/{run_id}/jobs"
    response = requests.get(url, headers=_github_headers(token), timeout=60)
    if response.status_code >= 400:
        _raise_github_error(response, "Workflow jobs lookup")
    jobs = response.json().get("jobs", [])
    return [
        {
            "id": job.get("id"),
            "name": job.get("name"),
            "conclusion": job.get("conclusion"),
            "status": job.get("status"),
            "started_at": job.get("started_at"),
            "completed_at": job.get("completed_at"),
        }
        for job in jobs
    ]


def _extract_logs_from_archive(
    content: bytes,
    failed_job_names: list[str] | None = None,
) -> str:
    """Extract log text from a GitHub Actions log zip archive."""
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            parts: list[str] = []
            normalized_failed = [_normalize_job_name(name) for name in (failed_job_names or [])]

            for name in sorted(archive.namelist()):
                if name.endswith("/"):
                    continue

                if normalized_failed:
                    folder = name.split("/", 1)[0]
                    folder_norm = _normalize_job_name(folder)
                    if not any(
                        failed in folder_norm or folder_norm in failed
                        for failed in normalized_failed
                    ):
                        continue

                file_content = archive.read(name).decode("utf-8", errors="replace")
                parts.append(f"=== {name} ===\n{file_content}")
    except zipfile.BadZipFile as exc:
        raise GitHubAPIError("GitHub returned an invalid log archive.") from exc

    if not parts:
        raise GitHubAPIError("No matching log files were found in the workflow run archive.")

    return "\n\n".join(parts)


def fetch_failed_job_logs(
    owner: str,
    repo: str,
    run_id: str | int,
    token: str,
) -> dict[str, Any]:
    """Fetch logs for failed jobs in a workflow run with run metadata."""
    numeric_run_id = validate_run_id(str(run_id)) if not isinstance(run_id, int) else run_id
    run = fetch_workflow_run(owner, repo, numeric_run_id, token)
    jobs = fetch_workflow_jobs(owner, repo, numeric_run_id, token)

    if run.get("status") != "completed":
        raise GitHubAPIError(
            f"Workflow run is still `{run.get('status')}`. Wait until it completes before fetching logs."
        )

    failed_jobs = [job["name"] for job in jobs if job.get("conclusion") == "failure"]
    if not failed_jobs and run.get("conclusion") == "failure":
        failed_jobs = [job["name"] for job in jobs if job.get("conclusion") not in {"success", "skipped", None}]

    logs_url = f"https://api.github.com/repos/{owner}/{repo}/actions/runs/{numeric_run_id}/logs"
    archive_bytes = _download_log_archive(logs_url, token)
    log_text = _extract_logs_from_archive(archive_bytes, failed_jobs or None)

    return {
        "log_text": log_text,
        "run": run,
        "jobs": jobs,
        "failed_job_names": failed_jobs,
        "workflow_path": run.get("workflow_path"),
    }


def fetch_workflow_logs(owner: str, repo: str, run_id: str | int, token: str) -> str:
    """Fetch and extract GitHub Actions workflow run logs for failed jobs."""
    result = fetch_failed_job_logs(owner, repo, run_id, token)
    return result["log_text"]


def fetch_workflow_yaml_for_run(
    owner: str,
    repo: str,
    run_id: str | int,
    token: str,
) -> tuple[str | None, str | None]:
    """Fetch workflow YAML content referenced by a workflow run."""
    numeric_run_id = validate_run_id(str(run_id)) if not isinstance(run_id, int) else run_id
    run = fetch_workflow_run(owner, repo, numeric_run_id, token)
    workflow_path = run.get("workflow_path")
    head_branch = run.get("head_branch") or _get_default_branch(owner, repo, token)

    if workflow_path:
        try:
            content = fetch_workflow_file(owner, repo, workflow_path, token, ref=head_branch)
            return workflow_path, content
        except requests.HTTPError:
            pass

    workflow_files = list_workflow_files(owner, repo, token)
    if not workflow_files:
        return None, None

    first_path = workflow_files[0]
    try:
        content = fetch_workflow_file(owner, repo, first_path, token, ref=head_branch)
        return first_path, content
    except requests.HTTPError:
        return first_path, None


def list_workflow_files(owner: str, repo: str, token: str) -> list[str]:
    """List workflow YAML files in .github/workflows/."""
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/.github/workflows"
    response = requests.get(url, headers=_github_headers(token), timeout=60)
    if response.status_code == 404:
        return []
    if response.status_code >= 400:
        _raise_github_error(response, "Workflow file listing")
    return [
        item["path"]
        for item in response.json()
        if item.get("type") == "file" and str(item.get("name", "")).endswith((".yml", ".yaml"))
    ]


def fetch_workflow_file(owner: str, repo: str, path: str, token: str, ref: str = "main") -> str:
    """Fetch a workflow or config file from a repository."""
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    response = requests.get(
        url,
        headers=_github_headers(token),
        params={"ref": ref},
        timeout=60,
    )
    if response.status_code >= 400:
        _raise_github_error(response, f"Workflow file fetch for `{path}`")
    payload = response.json()
    content = payload.get("content", "")
    if payload.get("encoding") == "base64" and content:
        return base64.b64decode(content).decode("utf-8", errors="replace")
    return str(content)


def _get_default_branch(owner: str, repo: str, token: str) -> str:
    """Return the repository default branch name."""
    url = f"https://api.github.com/repos/{owner}/{repo}"
    response = requests.get(url, headers=_github_headers(token), timeout=60)
    if response.status_code >= 400:
        _raise_github_error(response, "Repository lookup")
    return response.json().get("default_branch", "main")


def create_github_issue(
    owner: str,
    repo: str,
    title: str,
    body: str,
    token: str,
) -> str:
    """Create a GitHub issue with the DevOps analysis report."""
    url = f"https://api.github.com/repos/{owner}/{repo}/issues"
    response = requests.post(
        url,
        headers=_github_headers(token),
        json={"title": title, "body": body},
        timeout=60,
    )
    if response.status_code >= 400:
        _raise_github_error(response, "Issue creation")
    return response.json()["html_url"]


def create_fix_pull_request(
    owner: str,
    repo: str,
    file_path: str,
    content: str,
    title: str,
    body: str,
    token: str,
    base_branch: str | None = None,
) -> str:
    """Create a pull request with a suggested fix file on a new branch."""
    base_branch = base_branch or _get_default_branch(owner, repo, token)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    branch_name = f"devops-agent-fix-{timestamp}"

    ref_url = f"https://api.github.com/repos/{owner}/{repo}/git/ref/heads/{base_branch}"
    ref_response = requests.get(ref_url, headers=_github_headers(token), timeout=60)
    if ref_response.status_code >= 400:
        _raise_github_error(ref_response, "Base branch lookup")
    base_sha = ref_response.json()["object"]["sha"]

    create_ref_url = f"https://api.github.com/repos/{owner}/{repo}/git/refs"
    create_ref_response = requests.post(
        create_ref_url,
        headers=_github_headers(token),
        json={"ref": f"refs/heads/{branch_name}", "sha": base_sha},
        timeout=60,
    )
    if create_ref_response.status_code >= 400:
        _raise_github_error(create_ref_response, "Fix branch creation")

    file_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{file_path}"
    existing = requests.get(
        file_url,
        headers=_github_headers(token),
        params={"ref": base_branch},
        timeout=60,
    )
    payload: dict[str, str] = {
        "message": title,
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        "branch": branch_name,
    }
    if existing.status_code == 200:
        payload["sha"] = existing.json()["sha"]

    file_response = requests.put(
        file_url,
        headers=_github_headers(token),
        json=payload,
        timeout=60,
    )
    if file_response.status_code >= 400:
        _raise_github_error(file_response, "Fix file commit")

    pr_url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
    pr_response = requests.post(
        pr_url,
        headers=_github_headers(token),
        json={
            "title": title,
            "body": body,
            "head": branch_name,
            "base": base_branch,
        },
        timeout=60,
    )
    if pr_response.status_code >= 400:
        _raise_github_error(pr_response, "Pull request creation")
    return pr_response.json()["html_url"]
