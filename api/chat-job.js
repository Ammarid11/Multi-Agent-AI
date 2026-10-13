const proxyToCarl = require("../lib/carl-proxy");

module.exports = function handler(req, res) {
  if (req.method !== "GET") {
    res.setHeader("Allow", "GET");
    res.status(405).json({ detail: "Method Not Allowed" });
    return;
  }

  const requestUrl = new URL(req.url, "https://vercel.invalid");
  const jobId = requestUrl.searchParams.get("id");
  if (!jobId || !/^[a-f0-9]{32}$/.test(jobId)) {
    res.status(400).json({ detail: "A valid chat job ID is required." });
    return;
  }

  return proxyToCarl(req, res, `/api/chat/jobs/${encodeURIComponent(jobId)}`);
};
