import os
import sys
import glob
import subprocess
import tarfile
import tempfile


get_env = os.environ.get


def parse_patterns(patterns_input):
    if not patterns_input:
        return []

    # Treat as comma-delimited string (Woodpecker's default normalization for arrays)
    parsed = [p.strip() for p in patterns_input.split(',') if p.strip()]

    # Validation: Ensure patterns are relative and don't try to escape the workspace
    for pattern in parsed:
        if (
            os.path.isabs(pattern)
            or pattern.startswith("..")
            or "/../" in pattern
        ):
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
    enable_signed_url = str(get_env("PLUGIN_ENABLE_SIGNED_URL", "true")).lower() in ("true", "1", "yes")
    try:
        signed_url_expires_in = int(get_env("PLUGIN_SIGNED_URL_EXPIRES_IN", "604800"))
    except ValueError:
        print("Warning: Invalid PLUGIN_SIGNED_URL_EXPIRES_IN value, defaulting to 604800.")
        signed_url_expires_in = 604800

    # Woodpecker CI Environment Variables
    repo = get_env("CI_REPO")
    pipeline_num = get_env("CI_PIPELINE_NUMBER")
    # Use workflow number for the archive name
    workflow_num = get_env("CI_WORKFLOW_NUMBER", "0")
    local_archive = f"artifacts_{workflow_num}.tar.gz"

    # Validation: Bucket is always required to build the S3 URI
    if not bucket_name:
        print("Error: PLUGIN_BUCKET must be provided.")
        sys.exit(1)

    if not all([repo, pipeline_num]):
        print("Error: CI_REPO or CI_PIPELINE_NUMBER not found.")
        sys.exit(1)

    # Setup AWS Environment for the CLI only if keys are provided
    aws_env = os.environ.copy()
    if access_key:
        aws_env["AWS_ACCESS_KEY_ID"] = access_key
    if secret_key:
        aws_env["AWS_SECRET_ACCESS_KEY"] = secret_key
    if region:
        aws_env["AWS_DEFAULT_REGION"] = region

    # Construct the remote path
    remote_base = f"s3://{bucket_name}/{path_prefix.strip('/')}/{repo.strip('/')}/pipelines/{pipeline_num}/"

    # Base AWS command
    base_aws_cmd = ["aws"]
    if endpoint:
        base_aws_cmd.extend(["--endpoint-url", endpoint])
    base_aws_cmd.append("s3")

    if action == "upload":
        patterns = parse_patterns(patterns_raw)
        if not patterns:
            print("Error: patterns (list of strings) is required for upload.")
            sys.exit(1)

        files_to_archive = []
        for pattern in patterns:
            matched = glob.glob(pattern, recursive=True)
            files_to_archive.extend(matched)

        if not files_to_archive:
            print("No files found matching patterns. Skipping upload.")
            return

        print(f"Creating archive {local_archive}...")

        try:
            with tarfile.open(local_archive, "w:gz") as tar:
                for f in files_to_archive:
                    print(f"-> Adding {f}")
                    tar.add(f)
        except Exception as e:
            print(f"Failed to create archive: {e}")
            sys.exit(1)

        target_url = f"{remote_base.rstrip('/')}/{local_archive}"
        print(f"Uploading archive to {target_url}...")

        upload_cmd = base_aws_cmd + ["cp", local_archive, target_url]
        if run_command(upload_cmd, env=aws_env):
            print("Action 'upload' finished successfully.")
            # Clean up local archive
            os.remove(local_archive)

            if enable_signed_url:
                print("Generating presigned URL for artifact...")
                presign_cmd = base_aws_cmd + ["presign", target_url, "--expires-in", str(signed_url_expires_in)]
                try:
                    result = subprocess.run(presign_cmd, check=True, env=aws_env, capture_output=True, text=True)
                    print(f"Artifact Presigned URL (expires in {signed_url_expires_in}s):")
                    print(result.stdout.strip())
                except subprocess.CalledProcessError as e:
                    print(f"Warning: Failed to generate presigned URL. Exit code: {e.returncode}")
                    print(f"Stderr: {e.stderr}")
        else:
            sys.exit(1)

    elif action == "download":
        print(f"-> Syncing artifacts from {remote_base}")

        # Use a temporary directory for the sync process
        with tempfile.TemporaryDirectory(prefix="s3_artifacts_") as tmp_dir:
            sync_cmd = base_aws_cmd + ["sync", remote_base, tmp_dir]
            if not run_command(sync_cmd, env=aws_env):
                sys.exit(1)

            # Extract all tar.gz files found in the synced directory
            archives = glob.glob(os.path.join(tmp_dir, "*.tar.gz"))
            if not archives:
                print("No artifact archives found to download.")
            else:
                for archive in archives:
                    print(f"-> Extracting {os.path.basename(archive)}...")
                    try:
                        with tarfile.open(archive, "r:gz") as tar:
                            tar.extractall(path=".")
                    except Exception as e:
                        print(f"Failed to extract {archive}: {e}")
                        sys.exit(1)

        print("Action 'download' finished.")

    else:
        print(f"Error: Unknown action '{action}'.")
        sys.exit(1)


if __name__ == "__main__":
    main()