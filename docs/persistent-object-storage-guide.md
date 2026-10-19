# Persistent Object Storage: Backblaze B2 S3 API

## Intended use

Render's local filesystem is temporary staging/cache for this application. Use a private B2 bucket for persistent original uploads and canonical Parquet objects. The application keeps local filesystem mode for development and tests.

Set these backend settings when selecting S3 mode:

- STORAGE_BACKEND=s3
- S3_ENDPOINT_URL
- S3_BUCKET_NAME
- S3_REGION
- S3_ACCESS_KEY
- S3_SECRET_KEY
- S3_SIGNATURE_VERSION=s3v4

The endpoint, region, bucket, and key ID are configuration. The application key secret is sensitive and belongs only in the backend secret store. Do not use the B2 master key.

## Operations and required B2 capabilities

The implementation operates only on dataset objects under the datasets/ prefix.

| Application behavior | S3 operation | B2 capability |
| --- | --- | --- |
| Upload original or Parquet object | PutObject / multipart upload through boto3 upload helpers | writeFiles |
| Download an object | GetObject | readFiles |
| Check existence or size | HeadObject | readFiles |
| Delete one object by name | DeleteObject | writeFiles and deleteFiles |
| Delete all objects for one dataset | ListObjectsV2 then DeleteObjects | listFiles, writeFiles, and deleteFiles |
| `/ready` S3 availability check | `ListObjectsV2` with `Prefix="datasets/"` and `MaxKeys=1` | listFiles |

Create a standard application key restricted to the dedicated bucket and, where supported by the account setup, the datasets/ file-name prefix. Grant listFiles, readFiles, writeFiles, and deleteFiles only. Do not grant bucket creation, bucket deletion, bucket configuration, readBucket, or listAllBucketNames. The implementation no longer calls HeadBucket because Backblaze maps that API to listBuckets and a bucket-restricted key may need listAllBucketNames. Backblaze describes these mappings in [S3-compatible application key capabilities](https://www.backblaze.com/docs/cloud-storage-s3-compatible-app-keys).

`/health` is the lightweight liveness route and does not call storage. `/ready` checks the database and then performs a deeper, non-mutating storage availability check. In S3 mode it lists at most one key under `datasets/`, verifying S3 endpoint, bucket, credentials, and `listFiles` access. A listing failure makes readiness return `503`; this check does not verify object reads, writes, or deletes. It creates no health-probe objects, so repeated readiness requests cannot accumulate them. Actual object permissions still need to be validated through normal application operations with controlled test data. Local tests use Moto and do not contact B2.

## Object ownership and cleanup

Dataset object keys use this structure:

    datasets/<dataset UUID>/versions/v<number>/original/<sanitized filename>
    datasets/<dataset UUID>/versions/v<number>/data.parquet

The backend derives these keys from dataset and version identifiers. Prefix deletion for one dataset uses datasets/<dataset UUID>/ and leaves other datasets untouched. Account and dataset deletion require list and delete capabilities for cleanup.

The local staging/cache directory remains controlled by UPLOAD_DIR. Do not delete it as part of enabling B2. When switching an existing local deployment to B2, copy and verify existing objects using a separately reviewed migration procedure before changing STORAGE_BACKEND; no automatic copy occurs.

## Live verification

Before relying on B2, create the private bucket and restricted application key manually. Then confirm the bucket endpoint and region, test upload, download, HeadObject, list-by-prefix, individual and prefix deletion, and the `/ready` list check with non-sensitive test data. Verify that the account key does not access other buckets or prefixes. No real B2 account, key, bucket, or object was accessed in this local phase.
