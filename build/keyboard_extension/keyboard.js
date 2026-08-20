(function () {
  "use strict";

  const KB_LAYOUTS = {
    lower: [
      ["q", "w", "e", "r", "t", "y", "u", "i", "o", "p"],
      ["a", "s", "d", "f", "g", "h", "j", "k", "l"],
      ["⇧", "z", "x", "c", "v", "b", "n", "m", "⌫"],
      ["#+=", ",", "space", ".", "done"]
    ],
    upper: [
      ["Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P"],
      ["A", "S", "D", "F", "G", "H", "J", "K", "L"],
      ["⇧", "Z", "X", "C", "V", "B", "N", "M", "⌫"],
      ["#+=", ",", "space", ".", "done"]
    ],
    symbols: [
      ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"],
      ["!", "@", "#", "$", "%", "^", "&", "*", "(", ")"],
      ["-", "_", "=", "+", ":", ";", "'", "\"", "/", "?"],
      ["[", "]", "{", "}", "\\", "|", "~", "`", "⌫"],
      ["ABC", ",", "space", ".", "done"]
    ]
  };

  const TEXT_INPUT_TYPES = new Set([
    "text", "search", "email", "url", "tel", "password", "number", null, ""
  ]);

  function isTextField(el) {
    if (!el || !el.tagName) return false;
    const tag = el.tagName.toLowerCase();
    if (tag === "textarea") return !el.disabled && !el.readOnly;
    if (tag === "input") {
      return !el.disabled && !el.readOnly && TEXT_INPUT_TYPES.has(el.getAttribute("type"));
    }
    if (el.isContentEditable) return true;
    return false;
  }

  let kbMode = "lower";
  let activeEl = null;

  const kbHost = document.createElement("div");
  kbHost.id = "hak-keyboard";
  kbHost.className = "hak-hidden";

  function renderKeyboard() {
    const rows = KB_LAYOUTS[kbMode];
    const surface = document.createElement("div");
    surface.className = "hak-surface";
    rows.forEach(row => {
      const rowEl = document.createElement("div");
      rowEl.className = "hak-row";
      row.forEach(key => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "hak-key";
        if (key === "space") {
          btn.classList.add("hak-space");
          btn.textContent = " ";
        } else if (key === "done") {
          btn.classList.add("hak-accent", "hak-wide");
          btn.textContent = "Done";
        } else if (key === "⇧" || key === "#+=" || key === "ABC" || key === "⌫") {
          btn.classList.add("hak-wide");
          btn.textContent = key;
        } else {
          btn.textContent = key;
        }
        btn.dataset.key = key;
        rowEl.appendChild(btn);
      });
      surface.appendChild(rowEl);
    });
    kbHost.innerHTML = "";
    kbHost.appendChild(surface);
  }

  function insertText(el, text) {
    if (el.isContentEditable) {
      document.execCommand("insertText", false, text);
      return;
    }
    const start = el.selectionStart ?? el.value.length;
    const end = el.selectionEnd ?? el.value.length;
    const nativeSetter = Object.getOwnPropertyDescriptor(
      el.tagName.toLowerCase() === "textarea" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype,
      "value"
    ).set;
    nativeSetter.call(el, el.value.slice(0, start) + text + el.value.slice(end));
    const pos = start + text.length;
    try { el.setSelectionRange(pos, pos); } catch (e) { /* some input types don't support this */ }
    el.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
  }

  function backspace(el) {
    if (el.isContentEditable) {
      document.execCommand("delete", false);
      return;
    }
    const start = el.selectionStart ?? el.value.length;
    const end = el.selectionEnd ?? el.value.length;
    const nativeSetter = Object.getOwnPropertyDescriptor(
      el.tagName.toLowerCase() === "textarea" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype,
      "value"
    ).set;
    let newValue, newPos;
    if (start === end && start > 0) {
      newValue = el.value.slice(0, start - 1) + el.value.slice(end);
      newPos = start - 1;
    } else {
      newValue = el.value.slice(0, start) + el.value.slice(end);
      newPos = start;
    }
    nativeSetter.call(el, newValue);
    try { el.setSelectionRange(newPos, newPos); } catch (e) { /* ignore */ }
    el.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
  }

  function handleKey(key) {
    if (!activeEl) return;
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
        backspace(activeEl);
        return;
      case "space":
        insertText(activeEl, " ");
        return;
      case "done":
        hideKeyboard();
        activeEl.blur();
        return;
      default:
        insertText(activeEl, key);
    }
  }

  function showKeyboard(el) {
    activeEl = el;
    kbMode = "lower";
    renderKeyboard();
    kbHost.classList.remove("hak-hidden");
  }

  function hideKeyboard() {
    kbHost.classList.add("hak-hidden");
    activeEl = null;
  }

  kbHost.addEventListener("mousedown", e => e.preventDefault());
  kbHost.addEventListener("click", e => {
    const btn = e.target.closest(".hak-key");
    if (btn) handleKey(btn.dataset.key);
  });

  // document.activeElement does NOT drill into shadow roots - it stops at the
  // outermost shadow host (e.g. <ha-textfield>), not the real <input> inside
  // it. Home Assistant's fields are web components with their own shadow
  // roots, so comparing against document.activeElement directly made the
  // focusout hide-check think focus left every time it actually moved to
  // another real field (username -> password), hiding the keyboard
  // incorrectly. Walk into nested shadow roots to find the true focused
  // element, matching how composedPath()[0] already does for focusin.
  function getDeepActiveElement() {
    let el = document.activeElement;
    while (el && el.shadowRoot && el.shadowRoot.activeElement) {
      el = el.shadowRoot.activeElement;
    }
    return el;
  }

  document.addEventListener("focusin", e => {
    const el = e.composedPath()[0];
    if (isTextField(el)) showKeyboard(el);
  }, true);

  document.addEventListener("focusout", e => {
    const el = e.composedPath()[0];
    if (el === activeEl) {
      // Let a keyboard button's mousedown (which preventDefault()s) run first;
      // if focus didn't move to a real text field, hide.
      setTimeout(() => {
        const deepActive = getDeepActiveElement();
        if (!kbHost.contains(deepActive) && deepActive !== activeEl) {
          hideKeyboard();
        }
      }, 0);
    }
  }, true);

  function mount() {
    if (document.body) {
      document.body.appendChild(kbHost);
    } else {
      requestAnimationFrame(mount);
    }
  }
  mount();
})();
