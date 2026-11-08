import { createHash, createHmac } from "node:crypto";
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { homedir } from "node:os";
import { basename, dirname, extname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const CARD_ROOT = join(ROOT, "data", "images", "cards");
const SET_ROOT = join(ROOT, "data", "images", "sets");
const IMAGE_EXTENSIONS = new Set([".webp", ".jpg", ".jpeg", ".png"]);
const CONTENT_TYPES = {
  ".webp": "image/webp",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".png": "image/png",
};
const ALGORITHM = "AWS4-HMAC-SHA256";
const REGION = "auto";
const SERVICE = "s3";
const CACHE_CONTROL = "public, max-age=31536000, immutable";

function flag(name) {
  return process.argv.includes(name);
}

function value(name, fallback = null) {
  const index = process.argv.indexOf(name);
  return index >= 0 && process.argv[index + 1] ? process.argv[index + 1] : fallback;
}

function listImages(directory) {
  if (!existsSync(directory)) return [];
  return readdirSync(directory)
    .filter((name) => IMAGE_EXTENSIONS.has(extname(name).toLowerCase()))
    .sort()
    .map((name) => join(directory, name));
}

function cardJobs(setId) {
  const sets = setId
    ? [String(setId)]
    : existsSync(CARD_ROOT)
      ? readdirSync(CARD_ROOT, { withFileTypes: true })
          .filter((entry) => entry.isDirectory())
          .map((entry) => entry.name)
          .sort()
      : [];
  return sets.flatMap((name) =>
    listImages(join(CARD_ROOT, name)).map((path) => ({
      path,
      key: `cards/${name}/${basename(path)}`,
    })),
  );
}

function setJobs(setId) {
  const files = listImages(SET_ROOT);
  return files
    .filter((path) => !setId || basename(path).startsWith(`${setId}-`))
    .map((path) => ({ path, key: `sets/${basename(path)}` }));
}

function loadConfig() {
  const candidates = [
    process.env.PKMNDB_R2_CONFIG,
    join(homedir(), ".config", "pkmndb", "r2.json"),
  ].filter(Boolean);
  for (const path of candidates) {
    if (existsSync(path)) return JSON.parse(readFileSync(path, "utf8"));
  }
  const fromEnv =
    process.env.PKMNDB_R2_ACCOUNT_ID &&
    process.env.PKMNDB_R2_BUCKET &&
    process.env.PKMNDB_R2_ACCESS_KEY_ID &&
    process.env.PKMNDB_R2_SECRET_ACCESS_KEY &&
    process.env.PKMNDB_R2_PUBLIC_BASE_URL;
  if (fromEnv) {
    return {
      account_id: process.env.PKMNDB_R2_ACCOUNT_ID,
      bucket: process.env.PKMNDB_R2_BUCKET,
      access_key_id: process.env.PKMNDB_R2_ACCESS_KEY_ID,
      secret_access_key: process.env.PKMNDB_R2_SECRET_ACCESS_KEY,
      public_base_url: process.env.PKMNDB_R2_PUBLIC_BASE_URL,
    };
  }
  throw new Error(
    "No R2 credentials: set PKMNDB_R2_* env vars or provide ~/.config/pkmndb/r2.json",
  );
}

function sha256Hex(data) {
  return createHash("sha256").update(data).digest("hex");
}

function hmac(key, data) {
  return createHmac("sha256", key).update(data).digest();
}

function encodePath(key) {
  return key
    .split("/")
    .map((segment) =>
      encodeURIComponent(segment).replace(
        /[!'()*]/g,
        (character) => `%${character.charCodeAt(0).toString(16).toUpperCase()}`,
      ),
    )
    .join("/");
}

function signingKey(secret, date) {
  return hmac(hmac(hmac(hmac(`AWS4${secret}`, date), REGION), SERVICE), "aws4_request");
}

async function signedRequest(
  config,
  method,
  key,
  { body, contentType, cacheControl, allowNotFound = false } = {},
) {
  const host = `${config.account_id}.r2.cloudflarestorage.com`;
  const canonicalUri = `/${config.bucket}/${encodePath(key)}`;
  const now = new Date();
  const amzDate = now.toISOString().replace(/[:-]|\.\d{3}/g, "");
  const dateStamp = amzDate.slice(0, 8);
  const payload = body ?? Buffer.alloc(0);
  const payloadHash = sha256Hex(payload);
  const headers = {
    host,
    "x-amz-content-sha256": payloadHash,
    "x-amz-date": amzDate,
  };
  if (contentType) headers["content-type"] = contentType;
  if (cacheControl) headers["cache-control"] = cacheControl;
  const signedHeaders = Object.keys(headers).sort();
  const canonicalHeaders = signedHeaders.map((name) => `${name}:${headers[name]}\n`).join("");
  const canonicalRequest = [
    method,
    canonicalUri,
    "",
    canonicalHeaders,
    signedHeaders.join(";"),
    payloadHash,
  ].join("\n");
  const scope = `${dateStamp}/${REGION}/${SERVICE}/aws4_request`;
  const stringToSign = [ALGORITHM, amzDate, scope, sha256Hex(canonicalRequest)].join("\n");
  const signature = createHmac("sha256", signingKey(config.secret_access_key, dateStamp))
    .update(stringToSign)
    .digest("hex");
  const authorization = `${ALGORITHM} Credential=${config.access_key_id}/${scope}, SignedHeaders=${signedHeaders.join(";")}, Signature=${signature}`;
  const response = await fetch(`https://${host}${canonicalUri}`, {
    method,
    headers: {
      ...Object.fromEntries(
        signedHeaders.filter((name) => name !== "host").map((name) => [name, headers[name]]),
      ),
      Authorization: authorization,
    },
    body: method === "PUT" ? payload : undefined,
  });
  if (allowNotFound && response.status === 404) return response;
  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new Error(`R2 ${method} ${key} failed: HTTP ${response.status} ${detail.slice(0, 300)}`);
  }
  return response;
}

async function headObject(config, key) {
  const response = await signedRequest(config, "HEAD", key, { allowNotFound: true });
  if (response.status === 404) return null;
  return { size: Number(response.headers.get("content-length") ?? 0) };
}

async function putObject(config, key, body, contentType) {
  await signedRequest(config, "PUT", key, {
    body,
    contentType,
    cacheControl: CACHE_CONTROL,
  });
}

async function mapLimit(items, limit, fn) {
  const results = new Array(items.length);
  let next = 0;
  async function worker() {
    while (next < items.length) {
      const index = next++;
      results[index] = await fn(items[index], index);
    }
  }
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, worker));
  return results;
}

function publicUrl(config, key) {
  const base = (config.public_base_url || "").replace(/\/+$/, "");
  if (!base) throw new Error("R2 config has no public_base_url");
  return `${base}/${encodePath(key)}`;
}

async function verifyObject(config, job) {
  const response = await fetch(publicUrl(config, job.key));
  if (!response.ok) throw new Error(`${job.key}: HTTP ${response.status}`);
  const remote = Buffer.from(await response.arrayBuffer());
  const local = readFileSync(job.path);
  if (sha256Hex(remote) !== sha256Hex(local)) {
    throw new Error(`${job.key}: remote bytes do not match local file`);
  }
}

async function main() {
  const setId = value("--set");
  const kind = value("--kind", "all");
  const concurrency = Number(value("--concurrency", "8"));
  const dryRun = flag("--dry-run");
  const checkOnly = flag("--check-only");
  const verify = !flag("--no-verify");
  if (!["cards", "sets", "all"].includes(kind)) {
    throw new Error(`Unsupported --kind ${kind}`);
  }
  if (!Number.isInteger(concurrency) || concurrency < 1) {
    throw new Error(`Invalid --concurrency ${value("--concurrency")}`);
  }

  const jobs = [];
  if (kind === "cards" || kind === "all") jobs.push(...cardJobs(setId));
  if (kind === "sets" || kind === "all") jobs.push(...setJobs(setId));
  if (setId && jobs.length === 0) {
    throw new Error(`No local images found for set ${setId}`);
  }
  if (jobs.length === 0) {
    console.log("No local images found.");
    return 0;
  }

  if (dryRun) {
    for (const job of jobs) console.log(`would upload ${job.key}`);
    console.log(`dry run: ${jobs.length} files`);
    return 0;
  }

  const config = loadConfig();

  if (checkOnly) {
    let present = 0;
    let missing = 0;
    const failures = [];
    await mapLimit(jobs, concurrency, async (job) => {
      try {
        const localSize = statSync(job.path).size;
        const existing = await headObject(config, job.key);
        if (existing && existing.size === localSize) {
          present += 1;
          return;
        }
        missing += 1;
        console.log(
          `MISSING ${job.key} local=${localSize} remote=${existing ? existing.size : "absent"}`,
        );
      } catch (error) {
        failures.push(`${job.key}: ${error.message}`);
      }
    });
    console.log(
      `checked ${jobs.length} present ${present} missing ${missing} failed ${failures.length}`,
    );
    for (const failure of failures.slice(0, 10)) console.log(`FAILED ${failure}`);
    return failures.length || missing ? 1 : 0;
  }

  let uploaded = 0;
  let skipped = 0;
  const failures = [];
  const uploadedJobs = [];

  await mapLimit(jobs, concurrency, async (job) => {
    try {
      const bytes = readFileSync(job.path);
      const existing = await headObject(config, job.key);
      if (existing && existing.size === bytes.length) {
        skipped += 1;
        return;
      }
      const contentType = CONTENT_TYPES[extname(job.path).toLowerCase()] || "application/octet-stream";
      await putObject(config, job.key, bytes, contentType);
      uploaded += 1;
      uploadedJobs.push(job);
    } catch (error) {
      failures.push(`${job.key}: ${error.message}`);
    }
  });

  let verified = 0;
  if (verify) {
    for (const job of uploadedJobs.slice(0, 3)) {
      try {
        await verifyObject(config, job);
        verified += 1;
      } catch (error) {
        failures.push(`verify ${error.message}`);
      }
    }
  }

  console.log(
    `uploaded ${uploaded} skipped ${skipped} failed ${failures.length} verified ${verified} total ${jobs.length}`,
  );
  for (const failure of failures.slice(0, 10)) console.log(`FAILED ${failure}`);
  return failures.length ? 1 : 0;
}

try {
  process.exitCode = await main();
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
}
