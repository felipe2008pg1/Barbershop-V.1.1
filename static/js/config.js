const API_BASE = "https://barbershop-v-1-1.onrender.com";

/**
 * Escapes a value for safe insertion into HTML markup built via template
 * literals + innerHTML. This is the primary defense against stored/reflected
 * XSS (CWE-79): every piece of data that did not originate as a hardcoded
 * string in this codebase (user input, API responses) must go through this
 * before being placed inside innerHTML. The WAF on the backend is a
 * secondary layer, not a substitute for output encoding.
 */
function esc(value) {
  if (value === null || value === undefined) return "";
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
