// Kiosk Setup Wizard: builds kiosk-setup.json in the browser (no network calls).
// The kiosk's kiosk-import-setup.py reads it from the boot partition on first boot
// and applies it with the same code as the on-screen wizard (setup_wizard/server.py).
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const val = id => $(id).value.trim();
  const slugify = s => (s.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || 'kiosk');

  $('device_name').addEventListener('input', () => { $('slug_preview').textContent = 'kiosk/' + slugify($('device_name').value); });
  $('skip_wifi').addEventListener('change', () => { $('wifi_fields').hidden = $('skip_wifi').checked; });
  document.querySelectorAll('button.show').forEach(b => b.addEventListener('click', () => {
    const f = $(b.dataset.for); const show = f.type === 'password';
    f.type = show ? 'text' : 'password'; b.textContent = show ? 'Hide' : 'Show';
  }));

  function collect() {
    return {
      format: 'ha-kiosk-setup',
      version: 1,
      device_name: val('device_name'),
      dashboard_url: val('dashboard_url'),
      screensaver_url: val('screensaver_url'),
      screensaver_timeout: val('screensaver_timeout') || '300',
      dpms_timeout: val('dpms_timeout') || '600',
      rotation: $('rotation').value,
      touch_device: val('touch_device'),
      brightness_min: val('brightness_min') || '10',
      brightness_max: val('brightness_max') || '100',
      skip_wifi: $('skip_wifi').checked,
      wifi_ssid: $('skip_wifi').checked ? '' : $('wifi_ssid').value.trim(),
      wifi_password: $('skip_wifi').checked ? '' : $('wifi_password').value,
      wifi_hidden: !$('skip_wifi').checked && $('wifi_hidden').checked,
      wifi_country: val('wifi_country').toUpperCase(),
      mqtt: { host: val('mqtt_host'), port: val('mqtt_port') || '1883', username: val('mqtt_username'), password: $('mqtt_password').value },
      sensors: { c4001: $('sensor_c4001').checked, rcwl: $('sensor_rcwl').checked, lux: $('sensor_lux').checked },
      terminal_password: $('terminal_password').value,
      ssh_pubkey: val('ssh_pubkey'),
    };
  }

  function check(d) {
    const e = [];
    if (!d.device_name) e.push(['device_name', 'Give the kiosk a name, for example Kitchen.']);
    if (!/^https?:\/\/\S+$/.test(d.dashboard_url)) e.push(['dashboard_url', 'The dashboard URL must start with http:// or https://.']);
    if (d.screensaver_url && !/^https?:\/\/\S+$/.test(d.screensaver_url)) e.push(['screensaver_url', 'The screensaver URL must start with http:// or https://, or be empty.']);
    if (!d.skip_wifi && !d.wifi_ssid) e.push(['wifi_ssid', 'Enter the Wi-Fi network name, or tick "Ethernet only".']);
    if (d.wifi_country && !/^[A-Z]{2}$/.test(d.wifi_country)) e.push(['wifi_country', 'Wi-Fi country is two letters, for example US or GB.']);
    if (d.terminal_password && d.terminal_password.length < 8) e.push(['terminal_password', 'The new terminal password needs at least 8 characters.']);
    if (d.ssh_pubkey && !/^(ssh-(ed25519|rsa|dss)|ecdsa-sha2-\S+)\s+\S+/.test(d.ssh_pubkey)) e.push(['ssh_pubkey', 'That does not look like an SSH public key (it starts with ssh-ed25519, ssh-rsa or ecdsa-…).']);
    const any = Object.values(d.sensors).some(Boolean);
    if (any && !d.mqtt.host) e.push(['mqtt_host', 'Sensors report over MQTT: enter the broker host, or untick the sensors.']);
    const min = +d.brightness_min, max = +d.brightness_max;
    if (!(min >= 0 && max <= 100 && min <= max)) e.push(['brightness_min', 'Brightness min and max must be 0-100, with min not above max.']);
    return e;
  }

  $('wizard').addEventListener('submit', ev => {
    ev.preventDefault();
    document.querySelectorAll('.invalid').forEach(n => n.classList.remove('invalid'));
    const d = collect(); const errs = check(d); const box = $('errors');
    if (errs.length) {
      box.innerHTML = '<p>Fix these first:</p><ul>' + errs.map(([, m]) => `<li>${m.replace(/</g, '&lt;')}</li>`).join('') + '</ul>';
      box.hidden = false; $('done').hidden = true;
      errs.forEach(([id]) => $(id).classList.add('invalid'));
      $(errs[0][0]).focus();
      return;
    }
    box.hidden = true;
    const blob = new Blob([JSON.stringify(d, null, 2) + '\n'], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob); a.download = 'kiosk-setup.json';
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    $('done').hidden = false;
  });
})();
