#!/usr/bin/env python3
"""Build, verify, and deploy the invoice-reimbursement local release."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import py_compile
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_NAME = "invoice-reimbursement"
PAYLOAD_ROOT = REPO_ROOT / "skill" / SKILL_NAME
MANIFEST_PATH = REPO_ROOT / "release" / "manifest.json"
CODEX_HOME = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
DEFAULT_GIT = Path(r"C:\Program Files\Git\cmd\git.exe")
DEFAULT_PYTHON = CODEX_HOME / "toolchains" / "skill-creator" / "Scripts" / "python.exe"
DEFAULT_PREFLIGHT = CODEX_HOME / "helpers" / "Test-CodexSkillToolchain.ps1"
DEFAULT_PWSH = Path(r"C:\Program Files\PowerShell\7\pwsh.exe")
DEFAULT_VALIDATOR = CODEX_HOME / "skills" / ".system" / "skill-creator" / "scripts" / "quick_validate.py"


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def normalized_relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def included_files(root: Path, *, repository: bool = False) -> list[Path]:
    files = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        parts = relative.parts
        if ".git" in parts or "__pycache__" in parts or path.suffix == ".pyc":
            continue
        if repository:
            posix = relative.as_posix()
            if posix == "release/manifest.json" or posix.startswith("release/dist/"):
                continue
        if path.name == ".skill-lifecycle-state.json":
            continue
        files.append(path)
    return sorted(files, key=lambda item: normalized_relative(root, item))


def entries(root: Path, paths: list[Path]) -> list[dict[str, object]]:
    return [
        {
            "path": normalized_relative(root, path),
            "sha256": file_hash(path),
            "size": path.stat().st_size,
        }
        for path in paths
    ]


def aggregate(items: list[dict[str, object]]) -> str:
    digest = hashlib.sha256()
    for item in sorted(items, key=lambda value: str(value["path"])):
        digest.update(str(item["path"]).encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(item["sha256"]).upper().encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest().upper()


def run(command: list[str], *, cwd: Path | None = None, expected: int = 0) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )
    if result.returncode != expected:
        raise RuntimeError(
            f"Command failed ({result.returncode}): {' '.join(command)}\n{result.stdout}{result.stderr}"
        )
    return result


def load_manifest() -> dict:
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or data.get("skill_name") != SKILL_NAME:
        raise ValueError("Invalid release manifest")
    return data


def cmd_manifest(args: argparse.Namespace) -> None:
    payload = entries(PAYLOAD_ROOT, included_files(PAYLOAD_ROOT))
    repository = entries(REPO_ROOT, included_files(REPO_ROOT, repository=True))
    manifest = {
        "schema_version": 1,
        "skill_name": SKILL_NAME,
        "version": args.version,
        "tag": args.tag,
        "payload_root": f"skill/{SKILL_NAME}",
        "payload_files": payload,
        "payload_aggregate_sha256": aggregate(payload),
        "repository_files": repository,
        "released_content_aggregate_sha256": aggregate(repository),
    }
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    temporary = MANIFEST_PATH.with_name(f".{MANIFEST_PATH.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    os.replace(temporary, MANIFEST_PATH)
    print(json.dumps({"manifest": str(MANIFEST_PATH), "payload_files": len(payload)}, ensure_ascii=False))


def verify_hashes(manifest: dict) -> None:
    actual_payload_paths = [normalized_relative(PAYLOAD_ROOT, path) for path in included_files(PAYLOAD_ROOT)]
    listed_payload_paths = [str(item["path"]) for item in manifest["payload_files"]]
    if actual_payload_paths != listed_payload_paths:
        raise ValueError("Payload file set differs from manifest")
    for item in manifest["payload_files"]:
        path = PAYLOAD_ROOT / str(item["path"])
        if file_hash(path) != str(item["sha256"]).upper() or path.stat().st_size != int(item["size"]):
            raise ValueError(f"Payload mismatch: {item['path']}")
    if aggregate(manifest["payload_files"]) != manifest["payload_aggregate_sha256"]:
        raise ValueError("Payload aggregate mismatch")

    actual_repository_paths = [normalized_relative(REPO_ROOT, path) for path in included_files(REPO_ROOT, repository=True)]
    listed_repository_paths = [str(item["path"]) for item in manifest["repository_files"]]
    if actual_repository_paths != listed_repository_paths:
        raise ValueError("Repository release file set differs from manifest")
    for item in manifest["repository_files"]:
        path = REPO_ROOT / str(item["path"])
        if file_hash(path) != str(item["sha256"]).upper() or path.stat().st_size != int(item["size"]):
            raise ValueError(f"Repository file mismatch: {item['path']}")
    if aggregate(manifest["repository_files"]) != manifest["released_content_aggregate_sha256"]:
        raise ValueError("Released-content aggregate mismatch")


def verify_translation(manifest: dict) -> None:
    canonical = PAYLOAD_ROOT / "SKILL.md"
    mirror = (PAYLOAD_ROOT / "SKILL_ZH.md").read_text(encoding="utf-8")
    version = str(manifest["version"])
    source_hash = file_hash(canonical)
    if f"规范源版本：`{version}`" not in mirror:
        raise ValueError("SKILL_ZH.md source version is stale")
    if f"规范源 SHA-256：`{source_hash}`" not in mirror:
        raise ValueError("SKILL_ZH.md source hash is stale")
    canonical_text = canonical.read_text(encoding="utf-8")
    version_match = re.search(r'^\s*version:\s*["\']?([^"\'\r\n]+)', canonical_text, re.MULTILINE)
    if not version_match or version_match.group(1).strip() != version:
        raise ValueError("SKILL.md version differs from manifest")

    readme = REPO_ROOT / "README.md"
    readme_mirror = REPO_ROOT / "README_ZH.md"
    if readme.exists() != readme_mirror.exists():
        raise ValueError("README.md and README_ZH.md must exist together")
    if readme.exists():
        readme_mirror_text = readme_mirror.read_text(encoding="utf-8")
        if "规范源文件：`README.md`" not in readme_mirror_text:
            raise ValueError("README_ZH.md source filename is missing")
        if f"规范源版本：`{version}`" not in readme_mirror_text:
            raise ValueError("README_ZH.md source version is stale")
        if f"规范源 SHA-256：`{file_hash(readme)}`" not in readme_mirror_text:
            raise ValueError("README_ZH.md source hash is stale")

    policy = (PAYLOAD_ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")
    if not re.search(r"allow_implicit_invocation:\s*false\b", policy):
        raise ValueError("Candidate must be explicit-only")


def verify_toolchain(args: argparse.Namespace) -> None:
    run([str(args.pwsh), "-NoProfile", "-File", str(args.preflight)])
    run([str(args.python), "-B", "-X", "utf8", str(args.validator), str(PAYLOAD_ROOT)])
    with tempfile.TemporaryDirectory() as raw:
        temp = Path(raw)
        for index, source in enumerate(
            [
                PAYLOAD_ROOT / "scripts" / "invoice_state.py",
                REPO_ROOT / "tools" / "release.py",
                REPO_ROOT / "tests" / "test_invoice_state.py",
            ]
        ):
            py_compile.compile(str(source), cfile=str(temp / f"compiled-{index}.pyc"), doraise=True)
    run(
        [str(args.python), "-B", "-X", "utf8", "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"],
        cwd=REPO_ROOT,
    )


def verify_git(manifest: dict, args: argparse.Namespace) -> dict:
    status = run([str(args.git), "-C", str(REPO_ROOT), "status", "--porcelain=v1"]).stdout
    if status:
        raise ValueError(f"Repository is not clean:\n{status}")
    tag = run([str(args.git), "-C", str(REPO_ROOT), "describe", "--tags", "--exact-match", "HEAD"]).stdout.strip()
    if tag != manifest["tag"]:
        raise ValueError(f"HEAD tag mismatch: {tag}")
    tracked_raw = run([str(args.git), "-C", str(REPO_ROOT), "ls-files", "-z"]).stdout
    tracked = sorted(item for item in tracked_raw.split("\0") if item)
    expected = sorted([str(item["path"]) for item in manifest["repository_files"]] + ["release/manifest.json"])
    if tracked != expected:
        raise ValueError("Tracked files differ from release allowlist")
    remotes = [item for item in run([str(args.git), "-C", str(REPO_ROOT), "remote"]).stdout.splitlines() if item]
    if remotes:
        raise ValueError("Candidate repository unexpectedly has a remote")
    head = run([str(args.git), "-C", str(REPO_ROOT), "rev-parse", "HEAD"]).stdout.strip()
    return {"head": head, "tag": tag, "remote_count": 0}


def verify_runtime(manifest: dict, runtime: Path) -> None:
    if not runtime.is_dir():
        raise ValueError(f"Runtime is missing: {runtime}")
    actual = [normalized_relative(runtime, path) for path in included_files(runtime)]
    expected = [str(item["path"]) for item in manifest["payload_files"]]
    if actual != expected:
        raise ValueError("Runtime file set differs from manifest")
    for item in manifest["payload_files"]:
        if file_hash(runtime / str(item["path"])) != str(item["sha256"]).upper():
            raise ValueError(f"Runtime mismatch: {item['path']}")


def cmd_verify(args: argparse.Namespace) -> None:
    manifest = load_manifest()
    verify_hashes(manifest)
    verify_translation(manifest)
    verify_toolchain(args)
    git_result = verify_git(manifest, args)
    if args.runtime:
        verify_runtime(manifest, args.runtime.resolve())
    print(
        json.dumps(
            {
                "valid": True,
                "version": manifest["version"],
                "payload_files": len(manifest["payload_files"]),
                "payload_sha256": manifest["payload_aggregate_sha256"],
                "runtime_verified": bool(args.runtime),
                **git_result,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def cmd_build(args: argparse.Namespace) -> None:
    manifest = load_manifest()
    verify_hashes(manifest)
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for item in manifest["payload_files"]:
            source = PAYLOAD_ROOT / str(item["path"])
            arcname = f"{SKILL_NAME}/{item['path']}"
            info = zipfile.ZipInfo(arcname, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, source.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    print(json.dumps({"archive": str(output), "sha256": file_hash(output)}, ensure_ascii=False))


def copy_payload_to(manifest: dict, destination: Path) -> None:
    for item in manifest["payload_files"]:
        relative = Path(str(item["path"]))
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PAYLOAD_ROOT / relative, target)


def cmd_deploy(args: argparse.Namespace) -> None:
    manifest = load_manifest()
    verify_hashes(manifest)
    verify_translation(manifest)
    runtime = args.runtime.resolve()
    if runtime.name != SKILL_NAME:
        raise ValueError(f"Runtime directory must end with {SKILL_NAME}")
    runtime.parent.mkdir(parents=True, exist_ok=True)
    codex_home = runtime.parent.parent
    stage = runtime.parent / f".{SKILL_NAME}-stage-{uuid.uuid4().hex}"
    backup = codex_home / "backups" / "skill-deployments" / f"{SKILL_NAME}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    receipt_dir = codex_home / "receipts" / "skill-deployments"
    prior_moved = False
    installed = False
    try:
        stage.mkdir()
        copy_payload_to(manifest, stage)
        verify_runtime(manifest, stage)
        if runtime.exists():
            backup.parent.mkdir(parents=True, exist_ok=True)
            runtime.replace(backup)
            prior_moved = True
        stage.replace(runtime)
        installed = True
        verify_runtime(manifest, runtime)
    except Exception:
        if installed and runtime.exists():
            shutil.rmtree(runtime)
        if prior_moved and backup.exists():
            backup.replace(runtime)
        if stage.exists():
            shutil.rmtree(stage)
        raise

    receipt_dir.mkdir(parents=True, exist_ok=True)
    receipt = {
        "schema_version": 1,
        "skill_name": SKILL_NAME,
        "version": manifest["version"],
        "tag": manifest["tag"],
        "payload_aggregate_sha256": manifest["payload_aggregate_sha256"],
        "runtime": str(runtime),
        "backup": str(backup) if prior_moved else None,
        "installed_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    receipt_path = receipt_dir / f"{SKILL_NAME}-{uuid.uuid4().hex}.json"
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({**receipt, "receipt": str(receipt_path)}, ensure_ascii=False, indent=2))


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    sub = result.add_subparsers(dest="command", required=True)

    manifest = sub.add_parser("manifest")
    manifest.add_argument("--version", required=True)
    manifest.add_argument("--tag", required=True)
    manifest.set_defaults(func=cmd_manifest)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--git", type=Path, default=DEFAULT_GIT)
    common.add_argument("--python", type=Path, default=DEFAULT_PYTHON)
    common.add_argument("--pwsh", type=Path, default=DEFAULT_PWSH)
    common.add_argument("--preflight", type=Path, default=DEFAULT_PREFLIGHT)
    common.add_argument("--validator", type=Path, default=DEFAULT_VALIDATOR)

    verify = sub.add_parser("verify", parents=[common])
    verify.add_argument("--runtime", type=Path)
    verify.set_defaults(func=cmd_verify)

    build = sub.add_parser("build")
    build.add_argument("--output", type=Path, required=True)
    build.set_defaults(func=cmd_build)

    deploy = sub.add_parser("deploy")
    deploy.add_argument("--runtime", type=Path, required=True)
    deploy.set_defaults(func=cmd_deploy)
    return result


def main() -> None:
    args = parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
