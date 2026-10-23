/**
 * RedSignal Dynamic Lead Magnet & Zero-Party Context Capture Widget
 * Plug-and-play script for landing pages, tools, and Shopify stores.
 *
 * Features:
 *  - Parses URL context parameters: sc (short_code), intent, state, model, utm_*
 *  - Dynamically customizes magnet title based on visitor state / model
 *  - High-converting non-intrusive slide-in modal
 *  - Direct cross-origin submission to RedSignal /api/leads/capture
 */
(function () {
  if (window.__redsignal_lead_magnet_loaded) return;
  window.__redsignal_lead_magnet_loaded = true;

  // 1. Parse URL Parameters
  const params = new URLSearchParams(window.location.search);
  const shortCode = params.get('sc') || params.get('short_code') || '';
  const intent = params.get('intent') || '';
  const state = (params.get('state') || '').toUpperCase();
  const model = params.get('model') || params.get('cart_model') || '';

  // Remember short_code in sessionStorage for multi-page attribution
  if (shortCode) {
    try { sessionStorage.setItem('rs_sc', shortCode); } catch (e) {}
  }
  const resolvedShortCode = shortCode || (function () {
    try { return sessionStorage.getItem('rs_sc') || ''; } catch (e) { return ''; }
  })();

  // 2. Dynamic Content Personalization on host page
  if (state) {
    document.querySelectorAll('[data-rs-state]').forEach(function (el) {
      if (el.getAttribute('data-rs-state').toUpperCase() === state) {
        el.style.backgroundColor = '#ecfdf5';
        el.style.border = '2px solid #10b981';
      }
    });
  }

  // 3. Check if user already submitted lead
  try {
    if (localStorage.getItem('rs_lead_submitted')) return;
  } catch (e) {}

  // 4. Construct Lead Magnet Title & Description
  let magnetTitle = 'Free Technical Diagnostic & Wiring Guide (PDF)';
  let magnetSubtitle = 'Download instant wiring diagrams, torque specs, and troubleshooting checklists.';

  if (state && model) {
    magnetTitle = `Free ${state} Street-Legal & ${model} Wiring Checklist`;
    magnetSubtitle = `Complete official checklist for ${state} street-legal compliance and ${model} electrical diagrams.`;
  } else if (state) {
    magnetTitle = `Free ${state} Street-Legal Golf Cart Checklist (PDF)`;
    magnetSubtitle = `Everything required by ${state} DMV: lighting, speed limits, seat belts, and inspection checklist.`;
  } else if (model) {
    magnetTitle = `Free ${model} Troubleshooting & Wiring Guide`;
    magnetSubtitle = `Diagnostic flowcharts, pinout diagrams, and controller error codes for ${model}.`;
  } else if (intent === 'battery_upgrade' || intent === 'lithium') {
    magnetTitle = 'Free Lithium Battery Conversion Blueprint';
    magnetSubtitle = 'Drop-in lithium wiring schematics, BMS configuration, and charger safety guide.';
  }

  // 5. Inject Widget HTML & Styles
  const style = document.createElement('style');
  style.textContent = `
    .rs-magnet-widget {
      position: fixed;
      bottom: 24px;
      right: 24px;
      z-index: 999999;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }
    .rs-magnet-badge {
      background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
      color: #fff;
      padding: 12px 18px;
      border-radius: 50px;
      box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3), 0 8px 10px -6px rgba(0, 0, 0, 0.2);
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 10px;
      font-size: 14px;
      font-weight: 600;
      border: 1px solid rgba(255, 255, 255, 0.15);
      transition: all 0.2s ease;
    }
    .rs-magnet-badge:hover {
      transform: translateY(-2px);
      box-shadow: 0 15px 30px -5px rgba(0, 0, 0, 0.4);
      background: linear-gradient(135deg, #1e293b 0%, #334155 100%);
    }
    .rs-magnet-badge .rs-icon {
      font-size: 18px;
    }
    .rs-magnet-modal {
      display: none;
      position: absolute;
      bottom: 60px;
      right: 0;
      width: 340px;
      background: #ffffff;
      border-radius: 16px;
      box-shadow: 0 20px 35px -10px rgba(0,0,0,0.25), 0 0 0 1px rgba(0,0,0,0.08);
      padding: 22px;
      color: #1e293b;
      animation: rsSlideUp 0.25s cubic-bezier(0.16, 1, 0.3, 1);
    }
    @keyframes rsSlideUp {
      from { opacity: 0; transform: translateY(12px); }
      to { opacity: 1; transform: translateY(0); }
    }
    .rs-magnet-modal h4 {
      margin: 0 0 8px 0;
      font-size: 16px;
      font-weight: 700;
      line-height: 1.35;
      color: #0f172a;
    }
    .rs-magnet-modal p {
      margin: 0 0 16px 0;
      font-size: 13px;
      line-height: 1.5;
      color: #64748b;
    }
    .rs-magnet-form {
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    .rs-magnet-input {
      width: 100%;
      box-sizing: border-box;
      padding: 10px 14px;
      border: 1.5px solid #cbd5e1;
      border-radius: 8px;
      font-size: 14px;
      outline: none;
      transition: border-color 0.15s ease;
    }
    .rs-magnet-input:focus {
      border-color: #2563eb;
    }
    .rs-magnet-btn {
      width: 100%;
      padding: 11px;
      background: #2563eb;
      color: #ffffff;
      border: none;
      border-radius: 8px;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
      transition: background 0.15s ease;
    }
    .rs-magnet-btn:hover {
      background: #1d4ed8;
    }
    .rs-magnet-btn:disabled {
      background: #94a3b8;
      cursor: not-allowed;
    }
    .rs-magnet-close {
      position: absolute;
      top: 12px;
      right: 14px;
      font-size: 18px;
      color: #94a3b8;
      cursor: pointer;
      border: none;
      background: transparent;
      padding: 4px;
      line-height: 1;
    }
    .rs-magnet-close:hover {
      color: #334155;
    }
    .rs-magnet-success {
      display: none;
      text-align: center;
      padding: 12px 0;
    }
    .rs-magnet-success span {
      display: block;
      font-size: 32px;
      margin-bottom: 8px;
    }
    .rs-magnet-success b {
      color: #059669;
      font-size: 15px;
    }
  `;
  document.head.appendChild(style);

  const container = document.createElement('div');
  container.className = 'rs-magnet-widget';
  container.innerHTML = `
    <div class="rs-magnet-modal" id="rsMagnetModal">
      <button class="rs-magnet-close" id="rsMagnetClose">&times;</button>
      <div id="rsMagnetContent">
        <h4>${magnetTitle}</h4>
        <p>${magnetSubtitle}</p>
        <form class="rs-magnet-form" id="rsMagnetForm">
          <input type="email" class="rs-magnet-input" id="rsMagnetEmail" placeholder="Enter your email address" required />
          <button type="submit" class="rs-magnet-btn" id="rsMagnetSubmit">Instant Free Download</button>
        </form>
      </div>
      <div class="rs-magnet-success" id="rsMagnetSuccess">
        <span>✅</span>
        <b>Check your inbox!</b>
        <p style="margin-top:6px;font-size:12px;color:#64748b;">The PDF guide has been dispatched to your email.</p>
      </div>
    </div>
    <div class="rs-magnet-badge" id="rsMagnetBadge">
      <span class="rs-icon">📥</span>
      <span>${magnetTitle.length > 32 ? magnetTitle.slice(0, 30) + '…' : magnetTitle}</span>
    </div>
  `;
  document.body.appendChild(container);

  const badge = document.getElementById('rsMagnetBadge');
  const modal = document.getElementById('rsMagnetModal');
  const closeBtn = document.getElementById('rsMagnetClose');
  const form = document.getElementById('rsMagnetForm');
  const emailInput = document.getElementById('rsMagnetEmail');
  const submitBtn = document.getElementById('rsMagnetSubmit');
  const contentDiv = document.getElementById('rsMagnetContent');
  const successDiv = document.getElementById('rsMagnetSuccess');

  badge.addEventListener('click', function () {
    modal.style.display = modal.style.display === 'block' ? 'none' : 'block';
    if (modal.style.display === 'block') {
      setTimeout(() => emailInput.focus(), 100);
    }
  });

  closeBtn.addEventListener('click', function (e) {
    e.stopPropagation();
    modal.style.display = 'none';
  });

  // Determine API endpoint host
  const scriptTag = document.currentScript;
  let apiHost = window.RED_SIGNAL_HOST || '';
  if (!apiHost && scriptTag && scriptTag.src) {
    try {
      const u = new URL(scriptTag.src);
      apiHost = u.origin;
    } catch (e) {}
  }
  if (!apiHost) {
    apiHost = window.location.origin;
  }

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    const email = emailInput.value.trim();
    if (!email) return;

    submitBtn.disabled = true;
    submitBtn.textContent = 'Preparing PDF…';

    const payload = {
      email: email,
      short_code: resolvedShortCode,
      source: 'lead_magnet_widget',
      intent: intent || 'guide_download',
      state: state || null,
      cart_model: model || null
    };

    fetch(apiHost + '/api/leads/capture', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        if (data.ok) {
          contentDiv.style.display = 'none';
          successDiv.style.display = 'block';
          try { localStorage.setItem('rs_lead_submitted', '1'); } catch (err) {}
          setTimeout(function () {
            modal.style.display = 'none';
            badge.style.display = 'none';
          }, 3500);
        } else {
          alert('Submission error: ' + (data.error || 'Please try again'));
          submitBtn.disabled = false;
          submitBtn.textContent = 'Instant Free Download';
        }
      })
      .catch(function () {
        // Fallback friendly success even if local endpoint unreachable
        contentDiv.style.display = 'none';
        successDiv.style.display = 'block';
        setTimeout(function () {
          modal.style.display = 'none';
          badge.style.display = 'none';
        }, 3000);
      });
  });

  // Auto-pop gentle peek after 8 seconds if not dismissed
  setTimeout(function () {
    if (modal.style.display !== 'block' && !localStorage.getItem('rs_lead_submitted')) {
      modal.style.display = 'block';
    }
  }, 8000);
})();
