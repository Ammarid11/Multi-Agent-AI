const assert = require("node:assert/strict");
const { afterEach, test } = require("node:test");

const chatJobHandler = require("./api/chat-job");
const chatJobsHandler = require("./api/chat-jobs");
const catchAllHandler = require("./api/[...path]");

const originalFetch = global.fetch;
const originalEnvironment = {
  CARL_API_URL: process.env.CARL_API_URL,
  NGROK_BASIC_AUTH_USERNAME: process.env.NGROK_BASIC_AUTH_USERNAME,
  NGROK_BASIC_AUTH_PASSWORD: process.env.NGROK_BASIC_AUTH_PASSWORD,
};

afterEach(() => {
  global.fetch = originalFetch;
  for (const [name, value] of Object.entries(originalEnvironment)) {
    if (value === undefined) {
      delete process.env[name];
    } else {
      process.env[name] = value;
    }
  }
});

function configureProxy() {
  process.env.CARL_API_URL = "https://carl.example";
  process.env.NGROK_BASIC_AUTH_USERNAME = "test-user";
  process.env.NGROK_BASIC_AUTH_PASSWORD = "test-password";
}

function createResponse() {
  return {
    headers: {},
    statusCode: undefined,
    body: undefined,
    status(statusCode) {
      this.statusCode = statusCode;
      return this;
    },
    setHeader(name, value) {
      this.headers[name.toLowerCase()] = value;
    },
    json(body) {
      this.body = body;
      this.ended = true;
      return this;
    },
    end(body) {
      this.body = body;
      this.ended = true;
      return this;
    },
  };
}

test("chat job start uses a single-segment Vercel route and forwards to Carl", async () => {
  configureProxy();
  let forwardedUrl;
  let forwardedOptions;
  global.fetch = async (url, options) => {
    forwardedUrl = url;
    forwardedOptions = options;
    return new Response('{"job_id":"0123456789abcdef0123456789abcdef","status":"queued"}', {
      status: 202,
      headers: { "content-type": "application/json" },
    });
  };
  const req = {
    method: "POST",
    url: "/api/chat-jobs",
    headers: { "content-type": "application/json" },
    body: { query: "hello" },
  };
  const res = createResponse();

  await chatJobsHandler(req, res);

  assert.equal(forwardedUrl.href, "https://carl.example/api/chat/jobs");
  assert.equal(forwardedOptions.method, "POST");
  assert.equal(forwardedOptions.body, '{"query":"hello"}');
  assert.equal(
    forwardedOptions.headers.get("authorization"),
    `Basic ${Buffer.from("test-user:test-password").toString("base64")}`,
  );
  assert.equal(res.statusCode, 202);
  assert.equal(res.body.toString(), '{"job_id":"0123456789abcdef0123456789abcdef","status":"queued"}');
});

test("chat job polling uses a single-segment Vercel route and forwards the ID", async () => {
  configureProxy();
  let forwardedUrl;
  global.fetch = async url => {
    forwardedUrl = url;
    return new Response('{"status":"running"}', {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  };
  const res = createResponse();

  await chatJobHandler(
    {
      method: "GET",
      url: "/api/chat-job?id=0123456789abcdef0123456789abcdef",
      headers: {},
    },
    res,
  );

  assert.equal(
    forwardedUrl.href,
    "https://carl.example/api/chat/jobs/0123456789abcdef0123456789abcdef",
  );
  assert.equal(res.statusCode, 200);
  assert.equal(res.body.toString(), '{"status":"running"}');
});

test("chat job polling rejects missing or malformed IDs without proxying", async () => {
  let fetchCalled = false;
  global.fetch = async () => {
    fetchCalled = true;
    throw new Error("Unexpected upstream request");
  };

  for (const url of ["/api/chat-job", "/api/chat-job?id=bad%2Fid"]) {
    const res = createResponse();
    await chatJobHandler({ method: "GET", url, headers: {} }, res);
    assert.equal(res.statusCode, 400);
    assert.deepEqual(res.body, { detail: "A valid chat job ID is required." });
  }
  assert.equal(fetchCalled, false);
});

test("existing one-segment API proxy behavior preserves its route and query", async () => {
  configureProxy();
  let forwardedUrl;
  global.fetch = async url => {
    forwardedUrl = url;
    return new Response('{"status":"online"}', {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  };
  const res = createResponse();

  await catchAllHandler(
    { method: "GET", url: "/api/status?details=1", headers: {} },
    res,
  );

  assert.equal(forwardedUrl.href, "https://carl.example/api/status?details=1");
  assert.equal(res.statusCode, 200);
});
