const proxyToCarl = require("../lib/carl-proxy");

module.exports = function handler(req, res) {
  if (req.method !== "POST") {
    res.setHeader("Allow", "POST");
    res.status(405).json({ detail: "Method Not Allowed" });
    return;
  }

  return proxyToCarl(req, res, "/api/chat/jobs");
};
