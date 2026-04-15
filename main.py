import os
import sys
import glob
import subprocess
import tempfile
import urllib.parse
import hashlib
from enum import Enum


class Scope(Enum):
    PIPELINE = "pipeline"
    REPOSITORY = "repository"


get_env = os.environ.get


def get_cache_id(cache_key_raw, cache_files_raw):
    """Resolves the Cache ID based on manual key or file hashes."""
    if cache_key_raw:
        # Interpolate environment variables like $CI_COMMIT_BRANCH
        return os.path.expandvars(cache_key_raw)

    if cache_files_raw:
        patterns = [p.strip() for p in cache_files_raw.split(",") if p.strip()]
        hasher = hashlib.sha256()

        # Expand globs and sort to ensure deterministic hashing
        matched_files = []
        for pattern in patterns:
            matches = glob.glob(pattern, recursive=True)
            matched_files.extend(matches)

        # Filter out directories and sort for consistency
        files = sorted(list(set(f for f in matched_files if os.path.isfile(f))))

        if not files:
            print(
                f"Error: No files matched the patterns provided in CACHE_KEY_FILES: {patterns}"
            )
            sys.exit(1)

        for fpath in files:
            with open(fpath, "rb") as f:
                while chunk := f.read(8192):
                    hasher.update(chunk)
        return hasher.hexdigest()

    return None


def format_size(size_bytes):
    """Formats bytes into a human-readable string."""
    if size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB")
    import math

    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_name[i]}"


def encode_every_character(text):
    """Encodes every character in the string to hex %XX format to bypass log maskers."""
    return "".join("%{:02X}".format(b) for b in text.encode("utf-8"))


def parse_patterns(patterns_input):
    if not patterns_input:
        return []

    # Treat as comma-delimited string (Woodpecker's default normalization for arrays)
    parsed = [p.strip() for p in patterns_input.split(",") if p.strip()]

    # Validation: Ensure patterns are relative and don't try to escape the workspace
    for pattern in parsed:
        if os.path.isabs(pattern) or pattern.startswith("..") or "/../" in pattern:
            print(
                f"Error: Pattern '{pattern}' is invalid. Only relative paths within the workspace are allowed."
            )
            sys.exit(1)

    return parsed


def run_command(cmd, env=None):
    """Helper to run shell commands and exit on failure."""
    try:
        subprocess.run(cmd, check=True, env=env, capture_output=True, text=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Command failed with exit code {e.returncode}")
        print(f"Stderr: {e.stderr}")
        return False


def main():
    # Settings from Woodpecker
    action = get_env("PLUGIN_ACTION", "upload").lower()
    endpoint = get_env("PLUGIN_ENDPOINT")
    region = get_env("PLUGIN_REGION")
    bucket_name = get_env("PLUGIN_BUCKET")
    access_key = get_env("PLUGIN_ACCESS_KEY")
    secret_key = get_env("PLUGIN_SECRET_KEY")
    path_prefix = get_env("PLUGIN_PATH_PREFIX", "artifacts")
    patterns_raw = get_env("PLUGIN_PATTERNS", "")
    enable_signed_url = str(get_env("PLUGIN_ENABLE_SIGNED_URL", "true")).lower() in (
        "true",
        "1",
        "yes",
    )
    try:
        signed_url_expires_in = int(get_env("PLUGIN_SIGNED_URL_EXPIRES_IN", "604800"))
    except ValueError:
        print(
            "Warning: Invalid PLUGIN_SIGNED_URL_EXPIRES_IN value, defaulting to 604800."
        )
        signed_url_expires_in = 604800

    # Woodpecker CI Environment Variables
    repo = get_env("CI_REPO")
    pipeline_num = get_env("CI_PIPELINE_NUMBER")
    # Use workflow number for the unique archive name
    workflow_num = get_env("CI_WORKFLOW_NUMBER", "0")

    # Validation: Bucket is always required to build the S3 URI
    if not bucket_name:
        print("Error: PLUGIN_BUCKET must be provided.")
        sys.exit(1)

    if not repo:
        print("Error: CI_REPO not found.")
        sys.exit(1)

    try:
        scope = Scope(get_env("PLUGIN_SCOPE", "pipeline").lower())
    except ValueError:
        print("Error: Invalid PLUGIN_SCOPE. Must be 'pipeline' or 'repository'.")
        sys.exit(1)
    cache_key_raw = get_env("PLUGIN_CACHE_KEY")
    cache_files_raw = get_env("PLUGIN_CACHE_KEY_FILES")

    cache_id = None
    if scope == Scope.REPOSITORY:
        cache_id = get_cache_id(cache_key_raw, cache_files_raw)
        if not cache_id:
            print(
                "Error: PLUGIN_CACHE_KEY or PLUGIN_CACHE_KEY_FILES required for repository scope."
            )
            sys.exit(1)
    else:
        if not pipeline_num:
            print("Error: CI_PIPELINE_NUMBER required for pipeline scope.")
            sys.exit(1)

    # Construct the remote path
    if scope == Scope.REPOSITORY:
        remote_base = (
            f"s3://{bucket_name}/{path_prefix.strip('/')}/{repo.strip('/')}/cache/"
        )
        remote_archive_name = f"{cache_id}.tar.gz"
    else:
        remote_base = f"s3://{bucket_name}/{path_prefix.strip('/')}/{repo.strip('/')}/pipelines/{pipeline_num}/"
        remote_archive_name = f"artifacts_{workflow_num}.tar.gz"

    # Setup AWS Environment for the CLI only if keys are provided
    aws_env = os.environ.copy()
    if access_key:
        aws_env["AWS_ACCESS_KEY_ID"] = access_key
    if secret_key:
        aws_env["AWS_SECRET_ACCESS_KEY"] = secret_key
    if region:
        aws_env["AWS_DEFAULT_REGION"] = region

    # Base AWS command
    base_aws_cmd = ["aws"]
    if endpoint:
        base_aws_cmd.extend(["--endpoint-url", endpoint])
    base_aws_cmd.append("s3")

    if action == "upload":
        # Check if this specific cache already exists on S3
        if scope == Scope.REPOSITORY and cache_id:
            target_url = f"{remote_base.rstrip('/')}/{remote_archive_name}"
            print(f"Checking for existing cache at {target_url}...")
            ls_cmd = base_aws_cmd + ["ls", target_url]
            check_result = subprocess.run(ls_cmd, env=aws_env, capture_output=True)

            if check_result.returncode == 0:
                print(f"Cache found on remote: {target_url}")
                print("Skipping archiving and upload.")
                return

        patterns = parse_patterns(patterns_raw)
        if not patterns:
            print("Error: patterns (list of strings) is required for upload.")
            sys.exit(1)

        files_to_archive = []
        for pattern in patterns:
            matched = glob.glob(pattern, recursive=True)
            files_to_archive.extend(matched)

        files_to_archive = [f for f in files_to_archive if os.path.exists(f)]

        if not files_to_archive:
            print("No files found matching patterns. Skipping upload.")
            return

        with tempfile.NamedTemporaryFile(suffix=".tar.gz") as tmp_archive:
            print(f"Creating archive {remote_archive_name}...")
            file_list = "\n".join(files_to_archive)
            tar_cmd = ["tar", "-cz", "--files-from=-", "-f", tmp_archive.name]
            try:
                subprocess.run(
                    tar_cmd, input=file_list, text=True, capture_output=True, check=True
                )
            except subprocess.CalledProcessError as e:
                print(f"Failed to create archive using tar: {e}")
                print(f"Stderr: {e.stderr}")
                sys.exit(1)

            file_size = os.path.getsize(tmp_archive.name)
            target_url = f"{remote_base.rstrip('/')}/{remote_archive_name}"
            print(f"\nUploading archive ({format_size(file_size)}) to {target_url}...")

            upload_cmd = base_aws_cmd + ["cp", tmp_archive.name, target_url]
            run_result = run_command(upload_cmd, env=aws_env)

        if not run_result:
            sys.exit(1)
        print("Action 'upload' finished successfully.")

        if enable_signed_url:
            presign_cmd = base_aws_cmd + [
                "presign",
                target_url,
                "--expires-in",
                str(signed_url_expires_in),
            ]
            try:
                result = subprocess.run(
                    presign_cmd, check=True, env=aws_env, capture_output=True, text=True
                )
                url = result.stdout.strip()

                # Parse URL to encode X-Amz-Credential and bypass Woodpecker masking
                parsed_url = urllib.parse.urlparse(url)
                query_params = urllib.parse.parse_qs(parsed_url.query)

                if "X-Amz-Credential" in query_params:
                    credential_raw = query_params["X-Amz-Credential"][0]
                    encoded_credential = encode_every_character(credential_raw)
                    query_params["X-Amz-Credential"] = [encoded_credential]

                    # Reconstruct query string manually to maintain the %XX encoding for all chars
                    new_query = "&".join(
                        [f"{k}={v[0]}" for k, v in query_params.items()]
                    )
                    url = parsed_url._replace(query=new_query).geturl()

                print(f"\nArtifact Download URL (expires in {signed_url_expires_in}s):")
                print(url)
            except subprocess.CalledProcessError as e:
                print(
                    f"Warning: Failed to generate presigned URL. Exit code: {e.returncode}"
                )
                print(f"Stderr: {e.stderr}")

    elif action == "download":
        with tempfile.TemporaryDirectory(prefix="s3_artifacts_") as tmp_dir:
            if scope == Scope.REPOSITORY:
                target_url = f"{remote_base.rstrip('/')}/{remote_archive_name}"
                print(f"-> Downloading artifact: {target_url}")
                download_cmd = base_aws_cmd + ["cp", target_url, tmp_dir]
            else:
                print(f"-> Syncing artifacts from {remote_base}")
                download_cmd = base_aws_cmd + ["sync", remote_base, tmp_dir]

            if not run_command(download_cmd, env=aws_env):
                # For repository scope, it's okay if the specific file doesn't exist (cache miss)
                if scope != Scope.REPOSITORY:
                    sys.exit(1)

            # Extract all tar.gz files found in the synced directory
            archives = glob.glob(os.path.join(tmp_dir, "*.tar.gz"))
            if not archives:
                print("No artifact archives found to download.")
            else:
                for archive in archives:
                    print(f"-> Extracting {os.path.basename(archive)}...")
                    extract_cmd = ["tar", "-xzf", archive, "-C", "."]
                    try:
                        subprocess.run(
                            extract_cmd, check=True, capture_output=True, text=True
                        )
                    except subprocess.CalledProcessError as e:
                        print(f"Failed to extract {archive}: {e}")
                        print(f"Stderr: {e.stderr}")
                        sys.exit(1)

        print("Action 'download' finished.")

    else:
        print(f"Error: Unknown action '{action}'.")
        sys.exit(1)


if __name__ == "__main__":
    main()
