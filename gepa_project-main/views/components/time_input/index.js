const root = document.body;
root.style.margin = "0";
root.style.padding = "0";
root.style.fontFamily = "sans-serif";
root.style.background = "transparent";
root.style.color = "#f3f4f6";

const postToParent = (message) => {
  window.parent.postMessage({ isStreamlitMessage: true, ...message }, "*");
};

const input = document.createElement("input");
input.type = "text";
input.inputMode = "numeric";
input.autocomplete = "off";
input.autocapitalize = "off";
input.spellcheck = false;
input.maxLength = 5;
input.placeholder = "00:00";
input.value = "00:00";
input.style.boxSizing = "border-box";
input.style.width = "100%";
input.style.padding = "0.65rem 0.85rem";
input.style.border = "1px solid rgba(255, 255, 255, 0.35)";
input.style.borderRadius = "0.5rem";
input.style.background = "rgba(255, 255, 255, 0.06)";
input.style.color = "#ffffff";
input.style.caretColor = "#ffffff";
input.style.fontSize = "1rem";
input.style.outline = "none";
input.style.letterSpacing = "0.08em";
input.style.fontVariantNumeric = "tabular-nums";
input.style.minHeight = "2.6rem";
input.style.lineHeight = "1.2";

const formatTime = (rawValue) => {
  const digits = String(rawValue || "").replace(/\D/g, "").slice(0, 4);
  if (digits.length === 0) {
    return "";
  }
  if (digits.length <= 2) {
    return digits.length === 2 ? `${digits}:` : digits;
  }
  return `${digits.slice(0, 2)}:${digits.slice(2)}`;
};

const syncValue = () => {
  const formatted = formatTime(input.value);
  if (input.value !== formatted) {
    input.value = formatted;
  }
  postToParent({ type: "streamlit:setComponentValue", dataType: "json", value: formatted || "00:00" });
};

input.addEventListener("keydown", (event) => {
  const allowedKeys = [
    "Backspace",
    "Delete",
    "ArrowLeft",
    "ArrowRight",
    "ArrowUp",
    "ArrowDown",
    "Tab",
    "Home",
    "End",
    "Enter",
  ];
  if (allowedKeys.includes(event.key) || event.ctrlKey || event.metaKey) {
    return;
  }
  if (!/^\d$/.test(event.key)) {
    event.preventDefault();
  }
});

input.addEventListener("input", syncValue);
input.addEventListener("blur", syncValue);

root.appendChild(input);
postToParent({ type: "streamlit:componentReady", apiVersion: 1 });
postToParent({ type: "streamlit:setFrameHeight", height: document.body.scrollHeight });
