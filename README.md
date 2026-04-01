# **woodpecker-artifacts-s3-plugin**

Woodpecker CI plugin to share artifacts between workflows, using S3 and compatible services.

## **Usage**

### **Upload**

Upload files (as discovered by glob patterns) for current running pipeline to shared S3 storage.

The plugin will also print a presigned link to download the artifact to woodpecker logs.

```yaml
steps:  
  upload:  
    image: ghcr.io/otani-sg/woodpecker-artifacts-s3-plugin  
    settings:  
      action: upload  
      bucket: my-bucket  
      patterns: [ "dist/**", "package.json" ]  
      access_key: { from_secret: s3_access_key }  
      secret_key: { from_secret: s3_secret_key }
```

### **Download**

This will download all uploaded artifacts so far for current running pipeline.

```yaml
steps:  
  download:  
    image: codenetjp/woodpecker-artifacts-s3-plugin  
    settings:  
      action: download  
      bucket: my-bucket  
      access_key: { from_secret: s3_access_key }  
      secret_key: { from_secret: s3_secret_key }
```

## **Settings**

| Name | Default | Description |
| :---- | :---- | :---- |
| action | upload | `upload` or `download`. |
| patterns | none | **Required** if action is `upload`. List of glob patterns to specify which files to upload. |
| bucket | none | **Required**. S3 bucket name. |
| endpoint | none | Custom S3 API endpoint. |
| region | none | S3 Region. |
| access_key | none | S3 Access Key. |
| secret_key | none | S3 Secret Key. |
| path_prefix | artifacts | Root directory in bucket. |
| enable_signed_url | true | Print a presigned URL after upload. |
| signed_url_expires_in | 604800 | Expiration in seconds. Default 1 week. |

## **Path Structure**

The plugin scopes uploads for each pipeline to its own folder.

```
{path_prefix}/{CI_REPO}/pipelines/{CI_PIPELINE_NUMBER}/artifacts_{CI_WORKFLOW_NUMBER}.tar.gz
```