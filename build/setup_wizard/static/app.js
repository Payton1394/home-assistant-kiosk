(function () {
  "use strict";

  // ---------- On-screen keyboard ----------
  const KB_LAYOUTS = {
    lower: [
      ["q","w","e","r","t","y","u","i","o","p"],
      ["a","s","d","f","g","h","j","k","l"],
      ["⇧","z","x","c","v","b","n","m","⌫"],
      ["#+=",",","space",".","done"]
    ],
    upper: [
      ["Q","W","E","R","T","Y","U","I","O","P"],
      ["A","S","D","F","G","H","J","K","L"],
      ["⇧","Z","X","C","V","B","N","M","⌫"],
      ["#+=",",","space",".","done"]
    ],
    symbols: [
      ["1","2","3","4","5","6","7","8","9","0"],
      ["!","@","#","$","%","^","&","*","(",")"],
      ["-","_","=","+",":",";","'","\"","/","?"],
      ["[","]","{","}","\\","|","~","`","⌫"],
      ["ABC",",","space",".","done"]
    ]
  };

  let kbMode = "lower";
  let activeInput = null;
  const kbEl = document.getElementById("keyboard");

  function renderKeyboard() {
    const rows = KB_LAYOUTS[kbMode];
    const surface = document.createElement("div");
    surface.className = "kb-surface";
    rows.forEach(row => {
      const rowEl = document.createElement("div");
      rowEl.className = "kb-row";
      row.forEach(key => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "kb-key";
        if (key === "space") { btn.classList.add("space"); btn.textContent = " "; }
        else if (key === "done") { btn.classList.add("accent", "wide"); btn.textContent = "Done"; }
        else if (key === "⇧" || key === "#+=" || key === "ABC" || key === "⌫") {
          btn.classList.add("wide");
          btn.textContent = key;
        } else {
          btn.textContent = key;
        }
        btn.dataset.key = key;
        rowEl.appendChild(btn);
      });
      surface.appendChild(rowEl);
    });
    kbEl.innerHTML = "";
    kbEl.appendChild(surface);
  }

  function insertAtCursor(input, text) {
    const start = input.selectionStart ?? input.value.length;
    const end = input.selectionEnd ?? input.value.length;
    input.value = input.value.slice(0, start) + text + input.value.slice(end);
    const pos = start + text.length;
    input.setSelectionRange(pos, pos);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  }

  function backspaceAtCursor(input) {
    const start = input.selectionStart ?? input.value.length;
    const end = input.selectionEnd ?? input.value.length;
    if (start === end && start > 0) {
      input.value = input.value.slice(0, start - 1) + input.value.slice(end);
      input.setSelectionRange(start - 1, start - 1);
    } else {
      input.value = input.value.slice(0, start) + input.value.slice(end);
      input.setSelectionRange(start, start);
    }
    input.dispatchEvent(new Event("input", { bubbles: true }));
  }

  function handleKey(key) {
    if (!activeInput) return;
    switch (key) {
      case "⇧":
        kbMode = kbMode === "lower" ? "upper" : "lower";
        renderKeyboard();
        return;
      case "#+=":
        kbMode = "symbols";
        renderKeyboard();
        return;
      case "ABC":
        kbMode = "lower";
        renderKeyboard();
        return;
      case "⌫":
        backspaceAtCursor(activeInput);
        return;
      case "space":
        insertAtCursor(activeInput, " ");
        return;
      case "done":
        hideKeyboard();
        activeInput.blur();
        return;
      default:
        insertAtCursor(activeInput, key);
    }
  }

  function showKeyboard(input) {
    activeInput = input;
    kbMode = "lower";
    renderKeyboard();
    kbEl.classList.remove("hidden");
    document.getElementById("app").style.paddingBottom = "260px";
  }

  function hideKeyboard() {
    kbEl.classList.add("hidden");
    activeInput = null;
  }

  kbEl.addEventListener("mousedown", e => e.preventDefault());
  kbEl.addEventListener("click", e => {
    const btn = e.target.closest(".kb-key");
    if (btn) handleKey(btn.dataset.key);
  });

  document.addEventListener("focusin", e => {
    const t = e.target;
    if (t.matches('input[type="text"], input[type="password"], input[type="url"], input[type="number"], textarea')) {
      showKeyboard(t);
    }
  });

  renderKeyboard();

  // ---------- Wi-Fi ----------
  let networks = [];
  let selectedSSID = null;
  let selectedSecure = false;

  const listEl = document.getElementById("network-list");
  const scanStatus = document.getElementById("scan-status");
  const manualSSID = document.getElementById("wifi_ssid_manual");

  function renderNetworks() {
    listEl.innerHTML = "";
    networks.forEach(n => {
      const item = document.createElement("div");
      item.className = "network-item" + (n.ssid === selectedSSID ? " selected" : "");
      item.innerHTML = `<span>${n.secure ? "🔒 " : ""}${escapeHtml(n.ssid)}</span><span class="sig">${n.signal}%</span>`;
      item.addEventListener("click", () => {
        selectedSSID = n.ssid;
        selectedSecure = n.secure;
        manualSSID.value = n.ssid;
        renderNetworks();
      });
      listEl.appendChild(item);
    });
  }

  function escapeHtml(s) {
    return s.replace(/[&<>"']/g, c => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" }[c]));
  }

  async function scanNetworks() {
    scanStatus.textContent = "Scanning…";
    try {
      const res = await fetch("/api/wifi/scan");
      const data = await res.json();
      networks = data.networks || [];
      renderNetworks();
      scanStatus.textContent = networks.length ? "" : "No networks found.";
    } catch (e) {
      scanStatus.textContent = "Scan failed.";
    }
  }

  document.getElementById("rescan-btn").addEventListener("click", scanNetworks);
  manualSSID.addEventListener("input", () => {
    selectedSSID = manualSSID.value.trim();
    renderNetworks();
  });

  const skipWifi = document.getElementById("skip_wifi");
  const wifiSection = document.getElementById("wifi-section");
  skipWifi.addEventListener("change", () => {
    wifiSection.classList.toggle("hidden", skipWifi.checked);
  });

  scanNetworks();

  // ---------- Pre-fill from existing config (reopened via kiosk-reconfigure) ----------
  async function loadCurrent() {
    try {
      const res = await fetch("/api/current");
      const d = await res.json();
      if (!d.has_existing_config && !d.wifi_connected) return;

      const set = (id, v) => { if (v !== undefined && v !== null && v !== "") document.getElementById(id).value = v; };
      set("device_name", d.device_name);
      set("dashboard_url", d.dashboard_url);
      set("screensaver_url", d.screensaver_url);
      set("rotation", d.rotation);
      set("touch_device", d.touch_device);
      set("brightness_min", d.brightness_min);
      set("brightness_max", d.brightness_max);
      set("screensaver_timeout", d.screensaver_timeout);
      set("dpms_timeout", d.dpms_timeout);
      if (d.mqtt) {
        set("mqtt_host", d.mqtt.host);
        set("mqtt_port", d.mqtt.port);
        set("mqtt_username", d.mqtt.username);
        set("mqtt_password", d.mqtt.password);
      }
      if (d.sensors) {
        document.getElementById("sensor_lux").checked = !!d.sensors.lux;
        document.getElementById("sensor_c4001").checked = !!d.sensors.c4001;
        document.getElementById("sensor_rcwl").checked = !!d.sensors.rcwl;
      }
      if (d.wifi_connected) {
        skipWifi.checked = true;
        wifiSection.classList.add("hidden");
        if (d.wifi_ssid) {
          selectedSSID = d.wifi_ssid;
          manualSSID.value = d.wifi_ssid;
          manualSSID.placeholder = `Currently: ${d.wifi_ssid} (leave checkbox above ticked to keep it)`;
        }
      }
    } catch (e) {
      // No existing config yet (first boot) - leave the form blank, that's normal.
    }
  }
  loadCurrent();

  // ---------- Form submit ----------
  const form = document.getElementById("setup-form");
  const banner = document.getElementById("banner");
  const overlay = document.getElementById("working-overlay");
  const workingText = document.getElementById("working-text");
  const saveBtn = document.getElementById("save-btn");

  function showBanner(messages) {
    banner.innerHTML = messages.map(m => `<div>${escapeHtml(m)}</div>`).join("");
    banner.classList.remove("hidden");
    banner.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function hideBanner() {
    banner.classList.add("hidden");
  }

  form.addEventListener("submit", async e => {
    e.preventDefault();
    hideBanner();
    hideKeyboard();

    const val = id => document.getElementById(id).value.trim();

    const newPassword = document.getElementById("terminal_password").value;
    const confirmPassword = document.getElementById("terminal_password_confirm").value;
    if (newPassword && newPassword !== confirmPassword) {
      showBanner(["The new terminal password and its confirmation don't match."]);
      return;
    }
    if (newPassword && newPassword.length < 8) {
      showBanner(["New terminal password must be at least 8 characters."]);
      return;
    }

    const payload = {
      terminal_password: newPassword,
      device_name: val("device_name"),
      dashboard_url: val("dashboard_url"),
      screensaver_url: val("screensaver_url"),
      skip_wifi: skipWifi.checked,
      wifi_ssid: selectedSSID || manualSSID.value.trim(),
      wifi_password: document.getElementById("wifi_password").value,
      rotation: document.getElementById("rotation").value,
      touch_device: val("touch_device"),
      brightness_min: val("brightness_min"),
      brightness_max: val("brightness_max"),
      screensaver_timeout: val("screensaver_timeout"),
      dpms_timeout: val("dpms_timeout"),
      mqtt: {
        host: val("mqtt_host"),
        port: val("mqtt_port"),
        username: val("mqtt_username"),
        password: document.getElementById("mqtt_password").value
      },
      sensors: {
        lux: document.getElementById("sensor_lux").checked,
        c4001: document.getElementById("sensor_c4001").checked,
        rcwl: document.getElementById("sensor_rcwl").checked
      },
      ssh_pubkey: document.getElementById("ssh_pubkey").value.trim()
    };

    saveBtn.disabled = true;
    overlay.classList.remove("hidden");
    workingText.textContent = payload.skip_wifi ? "Saving settings…" : "Joining Wi-Fi and saving settings…";

    try {
      const res = await fetch("/api/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (!data.ok) {
        overlay.classList.add("hidden");
        saveBtn.disabled = false;
        showBanner(data.errors || ["Something went wrong."]);
        return;
      }
      workingText.textContent = "All set! Rebooting into your dashboard…";
    } catch (err) {
      overlay.classList.add("hidden");
      saveBtn.disabled = false;
      showBanner(["Could not reach the setup service: " + err.message]);
    }
  });
})();
