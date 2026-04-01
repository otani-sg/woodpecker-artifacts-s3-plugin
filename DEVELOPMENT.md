# **Development and Testing**

This guide provides instructions for local development and testing of the Woodpecker S3 Artifact Plugin using MinIO as a local S3-compatible storage backend.

## **1. Local S3 Setup (MinIO)**

To test the plugin locally, you can run a MinIO server using Docker. This will act as your S3-compatible endpoint.

docker run --rm --network host -v .data:/data minio/minio server /data

* **Default Access Key:** minioadmin  
* **Default Secret Key:** minioadmin  
* **Default Endpoint:** http://localhost:9000 (or your machine's IP)

**Note:** Ensure you create a bucket named test-bucket in the MinIO console before running the plugin tests.

## **2. Building the Plugin**

Build the Docker image locally:

docker build -t codenetjp/woodpecker-artifacts-s3-plugin .

## **3. Testing Upload**

Run the following command to test the **upload** action. Replace the IP address in PLUGIN_ENDPOINT with your local machine's IP address.

```bash
docker run --rm \
  -e PLUGIN_ACTION=upload \
  -e PLUGIN_ENDPOINT=http://localhost:9000 \
  -e PLUGIN_REGION=us-east-1 \
  -e PLUGIN_BUCKET=test-bucket \
  -e PLUGIN_ACCESS_KEY=minioadmin \
  -e PLUGIN_SECRET_KEY=minioadmin \
  -e PLUGIN_PATTERNS='data/**' \
  -e CI_REPO=test_org/test_repo \
  -e CI_PIPELINE_NUMBER=2 \
  -e CI_WORKFLOW_NUMBER=1 \
  --network host \
  -v $(pwd):$(pwd) \
  -w $(pwd) \
  codenetjp/woodpecker-artifacts-s3-plugin
```

## **4. Testing Download**

Run the following command to test the **download** action. This will sync the archives from the specified pipeline and extract them into your current directory.

```bash
docker run --rm \
  -e PLUGIN_ACTION=download \
  -e PLUGIN_ENDPOINT=http://localhost:9000 \
  -e PLUGIN_REGION=us-east-1 \
  -e PLUGIN_BUCKET=test-bucket \
  -e PLUGIN_ACCESS_KEY=minioadmin \
  -e PLUGIN_SECRET_KEY=minioadmin \
  -e CI_REPO=test_org/test_repo \
  -e CI_PIPELINE_NUMBER=2 \
  --network host \
  -v $(pwd):$(pwd) \
  -w $(pwd) \
  codenetjp/woodpecker-artifacts-s3-plugin
```

## **Environment Variables Reference**

| Variable | Description |
| :---- | :---- |
| PLUGIN_ACTION | upload or download |
| PLUGIN_ENDPOINT | The S3 API endpoint |
| PLUGIN_BUCKET | The target S3 bucket |
| PLUGIN_PATTERNS | Comma-delimited list of glob patterns (upload only) |
| CI_REPO | Mock repository name |
| CI_PIPELINE_NUMBER | Mock pipeline ID |
| CI_WORKFLOW_NUMBER | Mock step ID (used for archive naming) |

