/* One public configuration point. Docker/production use the same-origin proxy. */
window.APP_CONFIG = window.APP_CONFIG || {
  apiBase: location.port === "5500" && ["localhost", "127.0.0.1"].includes(location.hostname)
    ? location.protocol + "//" + location.hostname + ":8000" : location.origin
};
