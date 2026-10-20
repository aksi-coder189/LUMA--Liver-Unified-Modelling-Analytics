// Same-origin client for the loopback model API.

async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(path, { cache: "no-store", ...options });
  } catch {
    throw new Error("The local model server is not responding. Start it with `python src/server.py`.");
  }
  let payload;
  try {
    payload = await response.json();
  } catch {
    throw new Error(`The local server returned an unreadable response (HTTP ${response.status}).`);
  }
  if (!response.ok) throw new Error(payload?.error?.message || payload?.error || `Local model returned HTTP ${response.status}.`);
  return payload;
}

export function requestHealth() {
  return request("/api/v1/health");
}

export function requestDemo() {
  return request("/api/v1/demo");
}

export function requestModel(data) {
  return request("/api/v1/model", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data)
  });
}
