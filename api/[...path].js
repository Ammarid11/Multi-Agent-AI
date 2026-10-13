const proxyToCarl = require("../lib/carl-proxy");

module.exports = function handler(req, res) {
  return proxyToCarl(req, res, req.url);
};
