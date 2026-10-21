export async function apiFetch(url, opts = {}) {
  const r = await fetch(url, opts);
  return r.json();
}

export async function saveConfig(cfg) {
  await apiFetch('/api/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(cfg),
  });
}

export async function generateListenerProfile(payload) {
  return apiFetch('/api/listeners/ai_generate_profile', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export async function generateProjectPersonas(payload) {
  return apiFetch('/api/listeners/generate_personas', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export async function generateProjectVisualAssets(payload) {
  return apiFetch('/api/listeners/generate_visual_assets', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export async function generateOffersMatrix(payload) {
  return apiFetch('/api/listeners/ai_generate_offers', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export async function aiIngestUrl(payload) {
  return apiFetch('/api/listeners/ai_ingest_url', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export async function getAuthProfile() {
  return apiFetch('/api/auth/profile');
}

export async function updateAuth(payload) {
  return apiFetch('/api/auth/update', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export async function getSystemStatus() {
  return apiFetch('/api/system/status');
}

export async function restartSystem() {
  return apiFetch('/api/system/restart', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
}


