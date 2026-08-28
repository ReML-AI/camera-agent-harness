#!/usr/bin/env python3
"""Stage and verify the models declared in ``third_party/manifest.yaml``.

Downloads happen only during this explicit setup command.  Runtime code must use the
staged paths and must never resolve model names over the network.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Iterable

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
MANIFEST = ROOT / "third_party" / "manifest.yaml"
UNRESOLVED = {"capture_at_run", "unresolved", None, ""}
CHUNK = 1 << 20


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def tree_sha256(path: Path) -> str:
    """Hash a directory from its relative file names and individual file hashes."""
    digest = hashlib.sha256()
    for item in sorted(candidate for candidate in path.rglob("*") if candidate.is_file()):
        relative = item.relative_to(path).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256_of(item).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def load_components() -> list[dict]:
    return yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))["components"]


def _artifact_specs(component: dict) -> Iterable[tuple[Path, str]]:
    yield ROOT / str(component["install_path"]), str(component.get("sha256", ""))
    for alternate in component.get("alternates", []):
        yield ROOT / str(alternate["install_path"]), str(alternate.get("sha256", ""))


def _state_of_ollama(component: dict) -> tuple[str, str]:
    source = component.get("source") or {}
    model = source.get("model")
    expected = str(component.get("model_layer_digest", component.get("sha256", "")))
    expected = expected.removeprefix("sha256:")
    if model in UNRESOLVED or expected in UNRESOLVED:
        return "UNRESOLVED", "Ollama model name or layer digest is not recorded"
    # Prefer the on-disk store: `ollama show` needs a running server, which is a
    # job-time condition, not a staging one. The blob is what must actually exist.
    store = os.environ.get("OLLAMA_MODELS")
    if store:
        blob = Path(store) / "blobs" / f"sha256-{expected}"
        if blob.is_file():
            return "OK", f"Ollama layer sha256:{expected} present in {store}"
    try:
        result = subprocess.run(
            ["ollama", "show", "--modelfile", str(model)],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return "MISSING", (
            "ollama model not found on disk and no ollama executable; set OLLAMA_MODELS "
            "to the model store or install the client"
        )
    if result.returncode:
        return "MISSING", f"Ollama model {model} is not installed"
    normalized = result.stdout.lower().replace("sha256-", "sha256:")
    if expected.lower() not in normalized:
        return "MISMATCH", f"Ollama model {model} does not reference layer sha256:{expected}"
    return "OK", f"Ollama layer sha256:{expected} verified"


def state_of(component: dict) -> tuple[str, str]:
    """Return ``(state, detail)`` for one component without network access."""
    source = component.get("source") or {}
    if source.get("type") == "ollama":
        return _state_of_ollama(component)

    install = component.get("install_path")
    if install in UNRESOLVED or str(install).startswith("$"):
        return "UNRESOLVED", "no concrete staging path is declared"

    problems: list[str] = []
    unresolved_hashes: list[str] = []
    for target, expected in _artifact_specs(component):
        relative = target.relative_to(ROOT).as_posix()
        if not target.exists():
            problems.append(f"missing {relative}")
            continue
        if expected in UNRESOLVED:
            unresolved_hashes.append(relative)
            continue
        if expected.startswith("not_applicable_multi_file_snapshot"):
            revision = source.get("revision")
            if revision in UNRESOLVED:
                unresolved_hashes.append(f"{relative} (snapshot revision unresolved)")
            elif not target.is_dir() or not any(item.is_file() for item in target.rglob("*")):
                problems.append(f"empty snapshot directory {relative}")
            continue
        actual = tree_sha256(target) if target.is_dir() else sha256_of(target)
        if actual != expected:
            return "MISMATCH", f"{relative}: expected {expected[:16]}… got {actual[:16]}…"

    if problems:
        return "MISSING", "; ".join(problems)
    if unresolved_hashes:
        return "STAGED", "present but SHA-256 is unresolved: " + ", ".join(unresolved_hashes)

    if source.get("type") == "git" and source.get("revision") not in UNRESOLVED:
        checkout = _git_checkout_path(component)
        if checkout is None or not (checkout / ".git").is_dir():
            return "MISSING", "declared git checkout metadata is missing"
        result = subprocess.run(
            ["git", "-C", str(checkout), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        actual_revision = result.stdout.strip()
        if result.returncode or actual_revision != str(source["revision"]):
            return "MISMATCH", (
                f"git revision expected {source['revision']} but found "
                f"{actual_revision or 'unreadable checkout'}"
            )
    return "OK", "all declared artifacts verified"


def _replace_target(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
    shutil.move(str(source), str(target))


def _fetch_url(component: dict) -> bool:
    source = component["source"]
    url = source.get("url")
    if url in UNRESOLVED:
        print("  ! no URL is recorded; nothing was fetched")
        return False
    target = ROOT / component["install_path"]
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".part")
    temporary.unlink(missing_ok=True)
    print(f"  downloading {url}")
    result = subprocess.run(["curl", "-fL", "--retry", "3", "-o", str(temporary), str(url)])
    if result.returncode:
        temporary.unlink(missing_ok=True)
        return False
    temporary.replace(target)
    return True


def _fetch_huggingface(component: dict) -> bool:
    source = component["source"]
    repo, revision = source.get("repo_id"), source.get("revision")
    if repo in UNRESOLVED or revision in UNRESOLVED:
        print("  ! Hugging Face repo_id/revision is not recorded")
        return False
    target = ROOT / component["install_path"]
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("  ! install requirements.txt first (huggingface_hub is unavailable)")
        return False
    target.mkdir(parents=True, exist_ok=True)
    print(f"  downloading pinned Hugging Face snapshot {repo}@{revision}")
    snapshot_download(repo_id=str(repo), revision=str(revision), local_dir=target)
    return True


def _fetch_ultralytics(component: dict) -> bool:
    model_name = component["source"].get("model") or Path(component["install_path"]).name
    target = ROOT / component["install_path"]
    try:
        from ultralytics import YOLO
    except ImportError:
        print("  ! install requirements.txt first (ultralytics is unavailable)")
        return False

    print(f"  resolving {model_name} once through Ultralytics")
    with tempfile.TemporaryDirectory(prefix="ultralytics-stage-") as temporary:
        previous = Path.cwd()
        try:
            os.chdir(temporary)
            resolved = YOLO(str(model_name))
        finally:
            os.chdir(previous)
        candidates = [Path(temporary) / str(model_name)]
        checkpoint = getattr(resolved, "ckpt_path", None)
        if checkpoint:
            candidates.insert(0, Path(checkpoint))
        downloaded = next((item for item in candidates if item.is_file()), None)
        if downloaded is None:
            print(f"  ! Ultralytics did not expose the resolved {model_name} checkpoint")
            return False
        _replace_target(downloaded, target)
    return True


def _git_checkout_path(component: dict) -> Path | None:
    declared = component["source"].get("checkout_path")
    if declared not in UNRESOLVED:
        return ROOT / str(declared)
    install = Path(component["install_path"])
    parts = install.parts
    if len(parts) >= 2 and parts[0] == "third_party":
        return ROOT.joinpath(*parts[:2])
    return None



def _apply_recorded_patches(component: dict, checkout: Path) -> None:
    """Apply any patch recorded for this component under third_party/patches/.

    A clean clone of Light-ASD at its pinned revision uses NumPy aliases removed in
    modern releases. Applying the recorded compatibility patch makes a fresh setup
    reproduce the validated source tree.
    """
    patch_dir = ROOT / "third_party" / "patches"
    if not patch_dir.is_dir():
        return
    prefix = str(component["component_id"]).replace("_", "-")
    for patch in sorted(patch_dir.glob(f"{prefix}*.patch")):
        result = subprocess.run(
            ["git", "-C", str(checkout), "apply", "--check", str(patch)],
            capture_output=True,
        )
        if result.returncode:
            print(f"  ! {patch.name} does not apply cleanly; leaving checkout untouched")
            continue
        subprocess.run(["git", "-C", str(checkout), "apply", str(patch)], check=True)
        print(f"  applied {patch.name}")


def _fetch_git(component: dict) -> bool:
    source = component["source"]
    repository = source.get("repository")
    checkout = _git_checkout_path(component)
    if repository in UNRESOLVED or checkout is None:
        print("  ! git repository or checkout path is not recorded")
        return False
    if checkout.exists():
        print(f"  ! {checkout.relative_to(ROOT)} already exists; refusing to replace or update it")
        _record_git_revision(component, checkout)
        return state_of(component)[0] == "OK"
    checkout.parent.mkdir(parents=True, exist_ok=True)
    command = ["git", "clone"]
    revision = source.get("revision")
    if revision not in UNRESOLVED:
        command.extend(["--branch", str(revision)])
    command.extend([str(repository), str(checkout)])
    print(f"  cloning {repository} into {checkout.relative_to(ROOT)}")
    if subprocess.run(command).returncode:
        return False
    if shutil.which("git-lfs"):
        subprocess.run(["git", "-C", str(checkout), "lfs", "pull"], check=False)
    _apply_recorded_patches(component, checkout)
    _record_git_revision(component, checkout)
    return state_of(component)[0] == "OK"


def _record_git_revision(component: dict, checkout: Path) -> None:
    result = subprocess.run(
        ["git", "-C", str(checkout), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    revision = result.stdout.strip()
    if result.returncode or not re.fullmatch(r"[0-9a-fA-F]{40}", revision):
        print("  ! cloned checkout revision could not be measured")
        return
    repository = str(component["source"]["repository"])
    text = MANIFEST.read_text(encoding="utf-8")
    blocks = re.split(r"(?=^  - component_id: )", text, flags=re.MULTILINE)
    changed = False
    for index, block in enumerate(blocks):
        if "      type: git\n" not in block or f"      repository: {repository}\n" not in block:
            continue
        updated = re.sub(
            r"(?m)^      revision: capture_at_run$",
            f"      revision: {revision}",
            block,
            count=1,
        )
        changed = changed or updated != block
        blocks[index] = updated
    if changed:
        MANIFEST.write_text("".join(blocks), encoding="utf-8")
        print(f"  recorded cloned revision {revision} in third_party/manifest.yaml")
    component["source"]["revision"] = revision


def _record_easyocr_hashes(target: Path) -> str:
    files = sorted(item for item in target.rglob("*") if item.is_file())
    if not files:
        raise RuntimeError("EasyOCR initialized without producing any model files")
    tree_digest = tree_sha256(target)
    artifact_lines = ["    artifacts:"]
    for item in files:
        artifact_lines.extend([
            f"      - path: {item.relative_to(target).as_posix()}",
            f"        sha256: {sha256_of(item)}",
            f"        bytes: {item.stat().st_size}",
        ])

    text = MANIFEST.read_text(encoding="utf-8")
    start = text.index("  - component_id: easyocr\n")
    match = re.search(r"(?m)^  - component_id: ", text[start + 1 :])
    end = start + 1 + match.start() if match else len(text)
    block = text[start:end]
    block = re.sub(r"(?m)^    sha256: .*?$", f"    sha256: {tree_digest}", block, count=1)
    block = re.sub(r"(?m)^    status: .*?$", "    status: staged_hash_verified", block, count=1)
    block = re.sub(r"(?m)^    artifacts:\n(?:      [^\n]*\n)*", "", block)
    marker = re.search(r"(?m)^    license:", block)
    if marker is None:
        raise RuntimeError("EasyOCR manifest entry has no license field")
    block = block[: marker.start()] + "\n".join(artifact_lines) + "\n" + block[marker.start() :]
    MANIFEST.write_text(text[:start] + block + text[end:], encoding="utf-8")
    print("  recorded EasyOCR model file hashes in third_party/manifest.yaml")
    return tree_digest


def _fetch_easyocr(component: dict) -> bool:
    try:
        import easyocr
    except ImportError:
        print("  ! install requirements.txt first (easyocr is unavailable)")
        return False
    target = ROOT / component["install_path"]
    print("  initializing one CPU EasyOCR reader to populate its setup cache")
    with tempfile.TemporaryDirectory(prefix="easyocr-cache-") as temporary:
        cache = Path(temporary)
        easyocr.Reader(["en"], gpu=False, model_storage_directory=str(cache), download_enabled=True)
        staged = cache / "staged"
        staged.mkdir()
        model_files = [item for item in cache.rglob("*") if item.is_file() and staged not in item.parents]
        if not model_files:
            print("  ! EasyOCR produced no cached model files")
            return False
        for item in model_files:
            relative = item.relative_to(cache)
            destination = staged / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, destination)
        _replace_target(staged, target)
    component["sha256"] = _record_easyocr_hashes(target)
    return True


def _print_manual_instruction(component: dict) -> None:
    source = component.get("source") or {}
    target = component.get("install_path", "capture_at_run")
    print(f"  ! {component['component_id']} requires a manual setup step")
    print(f"    target: {target}")
    instruction = " ".join(str(source.get("instruction", "")).split())
    if instruction and instruction not in UNRESOLVED:
        print(f"    action: {instruction}")
    if target not in UNRESOLVED and not str(target).startswith("$"):
        print(f"    verify bytes: sha256sum {target}")
        if component.get("sha256") in UNRESOLVED:
            print("    then replace this component's capture_at_run sha256 in third_party/manifest.yaml")


def fetch(component: dict) -> bool:
    """Fetch one component when its recorded source permits honest automation."""
    kind = (component.get("source") or {}).get("type")
    if kind == "url":
        return _fetch_url(component)
    if kind == "huggingface":
        return _fetch_huggingface(component)
    if kind == "ollama":
        model = component["source"].get("model")
        if model in UNRESOLVED:
            print("  ! Ollama model name is not recorded")
            return False
        try:
            return subprocess.run(["ollama", "pull", str(model)]).returncode == 0
        except FileNotFoundError:
            print("  ! ollama executable is not installed")
            return False
    if kind == "ultralytics_auto":
        return _fetch_ultralytics(component)
    if kind == "git":
        return _fetch_git(component)
    if kind == "easyocr_auto":
        return _fetch_easyocr(component)
    _print_manual_instruction(component)
    return False


def blocking_components(components: Iterable[dict]) -> list[tuple[str, str, str]]:
    """Components that must be staged before a run may proceed.

    A component declaring ``required_for_run: false`` is reported by the status listing
    but never blocks: it is implemented yet not wired into any pipeline stage, so an
    absent artifact cannot affect a result. Anything without that flag blocks by
    default, so the permissive case has to be stated deliberately in the manifest.
    """
    blocked = []
    for component in components:
        if component.get("required_for_run") is False:
            continue
        state, detail = state_of(component)
        if state != "OK":
            blocked.append((component["component_id"], state, detail))
    return blocked


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true", help="attempt every recorded setup fetch")
    parser.add_argument("--verify", action="store_true", help="exit non-zero unless every component verifies")
    args = parser.parse_args(argv)

    components = load_components()
    width = max(len(component["component_id"]) for component in components)
    manual_kinds = {"manual_onnx_export", "local_training"}

    for component in components:
        component_id = component["component_id"]
        state, detail = state_of(component)
        kind = (component.get("source") or {}).get("type")
        should_fetch = args.fetch and state != "OK"
        if should_fetch:
            print(f"{component_id:<{width}}  FETCHING")
            fetch(component)
            state, detail = state_of(component)
        elif args.verify and state != "OK" and kind in manual_kinds:
            _print_manual_instruction(component)
        print(f"{component_id:<{width}}  {state:<10} {detail}")

    blocked = blocking_components(components)
    print()
    if blocked:
        print("NOT READY:")
        for component_id, state, detail in blocked:
            print(f"  {component_id}: {state} — {detail}")
    else:
        print("All declared components are staged and verified.")
    return 1 if args.verify and blocked else 0


if __name__ == "__main__":
    sys.exit(main())
