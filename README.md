# **woodpecker-artifacts-s3-plugin**

[![Container Image Version](https://img.shields.io/badge/v0.3@sha256:a50483e51356613ee1b35f8e02077794ca64246629b45cd5410c6f13bf282546%20(attested)-green?label=ghcr.io%2Fotani-sg%2Fwoodpecker-artifacts-s3-plugin)](https://github.com/otani-sg/woodpecker-artifacts-s3-plugin/attestations/24475957)

Woodpecker CI plugin to share artifacts between workflows, using S3 and compatible services.

## **Usage**

### 1. Share artifacts between workflows of the same pipeline

#### **Upload**

Upload files (as discovered by glob patterns) for current running pipeline to shared S3 storage.

The plugin will also print a presigned link to download the artifact to woodpecker logs.

```yaml
steps:
  upload:
    image: ghcr.io/otani-sg/woodpecker-artifacts-s3-plugin:v0.3@sha256:a50483e51356613ee1b35f8e02077794ca64246629b45cd5410c6f13bf282546
    settings:
      action: upload
      bucket: my-bucket
      patterns: ["dist/**", "package.json"]
      access_key: { from_secret: s3_access_key }
      secret_key: { from_secret: s3_secret_key }
```

#### **Download**

This will download all uploaded artifacts so far for current running pipeline.

```yaml
steps:
  download:
    image: ghcr.io/otani-sg/woodpecker-artifacts-s3-plugin:v0.3@sha256:a50483e51356613ee1b35f8e02077794ca64246629b45cd5410c6f13bf282546
    settings:
      action: download
      bucket: my-bucket
      access_key: { from_secret: s3_access_key }
      secret_key: { from_secret: s3_secret_key }
```

### 2. Share artifacts between pipelines of the same repository

Use case: share build cache or dependency cache between pipelines.

```yaml
variables:
  - &artifact_plugin ghcr.io/otani-sg/woodpecker-artifacts-s3-plugin:v0.3@sha256:a50483e51356613ee1b35f8e02077794ca64246629b45cd5410c6f13bf282546
  - &artifact_plugin_base
    bucket: my-bucket
    access_key: { from_secret: s3_access_key }
    secret_key: { from_secret: s3_secret_key }

steps:
  - name: download-deps
    image: *artifact_plugin
    settings: &deps
      <<: *artifact_plugin_base
      action: download
      scope: repository
      cache_key_files: package-lock.json
      patterns:
      - node_modules/**
  //
  // Other build steps
  //
  - name: upload-deps
    image: *artifact_plugin
    settings:
      <<: *deps
      action: upload
```

## **Settings**

**Core configs:**

* **action:** (Default `upload`)
  * Specifies the operation: `upload` or `download`.
* **patterns:** (No default)
  * **Required** if action is `upload`. List of glob patterns to specify which files to upload.
* **bucket:** (No default)
  * **Required**. S3 bucket name.

**Scoping configs:**

* **scope:** (Default `pipeline`)
  * `pipeline` or `repository`. Whether uploaded artifacts are shared only within same pipeline, or across pipelines of the same repository.
* **cache_key:** (No default)
  * **Required** if scope is `repository`. Either `cache_key` or `cache_key_files` is required. Determine the file name of the artifact file. Support environment variable expansion using `${VAR}` syntax.
* **cache_key_files:** (No default)
  * **Required** if scope is `repository`. Either `cache_key` or `cache_key_files` is required. List of glob patterns. The hash of specified files are used to determine the file name of the artifact file.

**S3 connection configs:**

* **endpoint:** (No default)
  * Custom S3 API endpoint.
* **region:** (No default)
  * S3 Region.
* **access_key:** (No default)
  * S3 Access Key.
* **secret_key:** (No default)
  * S3 Secret Key.

**Optional configs:**

* **path_prefix:** (Default `artifacts`)
  * Root directory in bucket.
* **enable_signed_url:** (Default `true`)
  * Print a presigned URL after upload.
* **signed_url_expires_in:** (Default `604800`)
  * Expiration in seconds. Default 1 week.

## **Path Structure**

If scope is `pipeline`:

```
{path_prefix}/{CI_REPO}/pipelines/{CI_PIPELINE_NUMBER}/artifacts_{CI_PIPELINE_NUMBER}_{CI_WORKFLOW_NUMBER}.tar.gz
```

If scope is `repository`:

```
{path_prefix}/{CI_REPO}/shared/{CACHE_HASH}.tar.gz
```