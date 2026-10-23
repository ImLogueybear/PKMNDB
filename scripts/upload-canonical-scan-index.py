import argparse
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import boto3


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--key-prefix", default="scan/canonical")
    parser.add_argument("--config", default=r"C:\Users\blogu\.config\pkmndb\r2.json")
    parser.add_argument("--concurrency", type=int, default=16)
    return parser.parse_args()


def main():
    args = parse_args()
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    bucket = config["bucket"]
    endpoint = f"https://{config['account_id']}.r2.cloudflarestorage.com"
    source = Path(args.source)
    manifest_path = source / "index.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    shards = sorted(source.glob("*.bin"))
    prefix = args.key_prefix.strip("/")

    local = threading.local()

    def client():
        value = getattr(local, "client", None)
        if value is None:
            value = boto3.client(
                "s3",
                endpoint_url=endpoint,
                aws_access_key_id=config["access_key_id"],
                aws_secret_access_key=config["secret_access_key"],
                region_name="auto",
            )
            local.client = value
        return value

    probe = client().head_object(Bucket=bucket, Key="scan/pocketvault/base1.bin")
    shard_type = probe.get("ContentType") or "application/octet-stream"
    cache_control = probe.get("CacheControl") or "public, max-age=31536000, immutable"

    jobs = [(path, f"{prefix}/{path.name}", shard_type) for path in shards]

    def upload(job):
        path, key, mime = job
        client().put_object(
            Bucket=bucket,
            Key=key,
            Body=path.read_bytes(),
            ContentType=mime,
            CacheControl=cache_control,
        )
        return key

    uploaded = 0
    failed = []
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = {pool.submit(upload, job): job for job in jobs}
        for future in as_completed(futures):
            try:
                future.result()
                uploaded += 1
            except Exception as exc:
                failed.append((futures[future][1], str(exc)))
    if not failed:
        upload((manifest_path, f"{prefix}/index.json", "application/json"))
        uploaded += 1
    indexed = set(manifest["sets"])
    missing = sorted(set(path.stem for path in shards) ^ indexed)
    print(
        f"uploaded {uploaded} failed {len(failed)} total {len(jobs)} "
        f"manifest_sets {len(indexed)} shards {len(shards)} count {manifest['count']}"
    )
    if missing:
        print("manifest/files mismatch", missing[:20])
    for key, error in failed[:10]:
        print("FAILED", key, error)
    return 1 if failed or missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
