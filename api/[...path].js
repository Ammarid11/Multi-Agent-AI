function getRequestBody(req) {
  if (req.body === undefined || req.body === null) {
    return undefined;
  }

  if (Buffer.isBuffer(req.body) || typeof req.body === "string") {
    return req.body;
  }

  return JSON.stringify(req.body);
}

module.exports = async function handler(req, res) {
  const configuredApiUrl = process.env.CARL_API_URL;
  const username = process.env.NGROK_BASIC_AUTH_USERNAME;
  const password = process.env.NGROK_BASIC_AUTH_PASSWORD;

  if (!configuredApiUrl) {
    res.status(500).json({ detail: "CARL_API_URL is not configured." });
    return;
  }

  if (!username || !password) {
    res.status(500).json({
      detail: "NGROK_BASIC_AUTH_USERNAME and NGROK_BASIC_AUTH_PASSWORD must be configured.",
    });
    return;
  }

  let apiUrl;
  try {
    apiUrl = new URL(configuredApiUrl);
  } catch {
    res.status(500).json({ detail: "CARL_API_URL must be a valid URL." });
    return;
  }

  if (!["http:", "https:"].includes(apiUrl.protocol)) {
    res.status(500).json({ detail: "CARL_API_URL must use HTTP or HTTPS." });
    return;
  }

  const requestUrl = new URL(req.url, apiUrl.origin);
  if (requestUrl.origin !== apiUrl.origin || !requestUrl.pathname.startsWith("/api/")) {
    res.status(400).json({ detail: "Only Carl API routes can be proxied." });
    return;
  }

  const headers = new Headers({
    "ngrok-skip-browser-warning": "1",
    authorization: `Basic ${Buffer.from(`${username}:${password}`).toString("base64")}`,
  });
  if (req.headers["content-type"]) {
    headers.set("content-type", req.headers["content-type"]);
  }
  if (req.headers.accept) {
    headers.set("accept", req.headers.accept);
  }

  try {
    const upstream = await fetch(requestUrl, {
      method: req.method,
      headers,
      body: ["GET", "HEAD"].includes(req.method) ? undefined : getRequestBody(req),
      redirect: "manual",
    });

    res.status(upstream.status);
    for (const name of ["content-type", "content-disposition", "cache-control"]) {
      const value = upstream.headers.get(name);
      if (value) {
        res.setHeader(name, value);
      }
    }

    if (req.method === "HEAD" || upstream.status === 204 || upstream.status === 304) {
      res.end();
      return;
    }

    res.end(Buffer.from(await upstream.arrayBuffer()));
  } catch (error) {
    console.error("Carl API proxy request failed:", error);
    res.status(502).json({ detail: "Could not reach the Carl API tunnel." });
  }
};
