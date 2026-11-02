/*
 * Edytor wpisów na blogu: pasek formatowania (Markdown), wiele zdjęć w treści
 * (przycisk, przeciągnij-i-upuść, wklejanie ze schowka) oraz podgląd renderowany
 * przez serwer — dokładnie tak, jak wpis będzie wyglądał po publikacji.
 *
 * Konfiguracja przez atrybuty data-* elementu [data-blog-editor]:
 *   data-upload-url  -> endpoint przyjmujący pola "images" (multipart)
 *   data-preview-url -> endpoint zwracający {"html": ...} dla {"content": ...}
 */
(function () {
  "use strict";

  var root = document.querySelector("[data-blog-editor]");
  if (!root) return;

  var textarea = root.querySelector("textarea");
  var form = textarea.form;
  var csrfToken = form.querySelector("input[name=csrf_token]").value;
  var uploadUrl = root.getAttribute("data-upload-url");
  var previewUrl = root.getAttribute("data-preview-url");
  var fileInput = root.querySelector("[data-image-input]");
  var statusBox = root.querySelector("[data-editor-status]");
  var previewBox = root.querySelector("[data-preview]");
  var writePane = root.querySelector("[data-write-pane]");

  // ---------- wstawianie tekstu z zachowaniem historii cofania (Ctrl+Z) ----------
  function replaceSelection(text, selectFrom, selectTo) {
    textarea.focus();
    var start = textarea.selectionStart;
    // execCommand zachowuje cofanie w przeglądarce; gdy niedostępne — setRangeText.
    var ok = false;
    try { ok = document.execCommand("insertText", false, text); } catch (e) { ok = false; }
    if (!ok) textarea.setRangeText(text, textarea.selectionStart, textarea.selectionEnd, "end");
    if (typeof selectFrom === "number") {
      textarea.setSelectionRange(start + selectFrom, start + selectTo);
    }
    textarea.dispatchEvent(new Event("input", { bubbles: true }));
  }

  function selectedText() {
    return textarea.value.substring(textarea.selectionStart, textarea.selectionEnd);
  }

  // Otacza zaznaczenie znacznikami (np. **…**); bez zaznaczenia wstawia przykładowy tekst.
  function wrap(before, after, placeholder) {
    var sel = selectedText() || placeholder;
    replaceSelection(before + sel + after, before.length, before.length + sel.length);
  }

  // Rozszerza zaznaczenie do pełnych linii i dodaje prefiks do każdej z nich.
  function prefixLines(prefixFn, placeholder) {
    var value = textarea.value;
    var start = value.lastIndexOf("\n", textarea.selectionStart - 1) + 1;
    var end = value.indexOf("\n", textarea.selectionEnd);
    if (end === -1) end = value.length;
    textarea.setSelectionRange(start, end);
    var lines = (selectedText() || placeholder).split("\n");
    var result = lines.map(function (line, i) { return prefixFn(i) + line; }).join("\n");
    replaceSelection(result, 0, result.length);
  }

  // Wstawia blok (np. zdjęcie, linię poziomą) w osobnych akapitach.
  function insertBlock(text) {
    var before = textarea.value.substring(0, textarea.selectionStart);
    var lead = before === "" || /\n\n$/.test(before) ? "" : (/\n$/.test(before) ? "\n" : "\n\n");
    replaceSelection(lead + text + "\n\n");
  }

  var actions = {
    bold: function () { wrap("**", "**", "pogrubiony tekst"); },
    italic: function () { wrap("*", "*", "kursywa"); },
    h2: function () { prefixLines(function () { return "## "; }, "Nagłówek"); },
    h3: function () { prefixLines(function () { return "### "; }, "Podtytuł"); },
    ul: function () { prefixLines(function () { return "- "; }, "element listy"); },
    ol: function () { prefixLines(function (i) { return (i + 1) + ". "; }, "element listy"); },
    quote: function () { prefixLines(function () { return "> "; }, "cytat"); },
    link: function () {
      var url = window.prompt("Adres linku (https://…):", "https://");
      if (!url || url === "https://") return;
      var label = selectedText() || "tekst linku";
      replaceSelection("[" + label + "](" + url.trim() + ")", 1, 1 + label.length);
    },
    hr: function () { insertBlock("---"); },
    image: function () { fileInput.click(); },
    preview: function () { togglePreview(true); },
    write: function () { togglePreview(false); }
  };

  root.addEventListener("click", function (event) {
    var button = event.target.closest("[data-action]");
    if (!button || !root.contains(button)) return;
    event.preventDefault();
    var action = actions[button.getAttribute("data-action")];
    if (action) action();
  });

  textarea.addEventListener("keydown", function (event) {
    if (!(event.ctrlKey || event.metaKey)) return;
    var key = event.key.toLowerCase();
    if (key === "b") { event.preventDefault(); actions.bold(); }
    else if (key === "i") { event.preventDefault(); actions.italic(); }
    else if (key === "k") { event.preventDefault(); actions.link(); }
  });

  // ---------- zdjęcia: wiele naraz ----------
  function setStatus(message, isError) {
    statusBox.textContent = message || "";
    statusBox.className = "editor-status" + (isError ? " editor-status-error" : "");
  }

  function uploadImages(fileList) {
    var files = Array.prototype.filter.call(fileList, function (f) { return /^image\//.test(f.type); });
    if (!files.length) return;
    var data = new FormData();
    files.forEach(function (f) { data.append("images", f, f.name || "zdjecie.png"); });
    setStatus("Wysyłanie zdjęć (" + files.length + ")…");

    fetch(uploadUrl, {
      method: "POST",
      headers: { "X-CSRFToken": csrfToken },
      body: data,
      credentials: "same-origin"
    })
      .then(function (response) {
        return response.json().catch(function () {
          throw new Error(response.status === 413 ? "Zdjęcia są za duże." : "Błąd serwera (" + response.status + ").");
        });
      })
      .then(function (json) {
        var images = json.images || [];
        if (images.length) {
          var markdown = images.map(function (img) {
            var alt = (img.alt || "zdjęcie").replace(/[\[\]]/g, "");
            return "![" + alt + "](" + img.url + ")";
          }).join("\n\n");
          insertBlock(markdown);
        }
        var errors = (json.errors || []).concat(json.error ? [json.error] : []);
        if (errors.length) setStatus(errors.join(" · "), true);
        else setStatus("Dodano zdjęć: " + images.length + ".");
      })
      .catch(function (err) { setStatus(err.message || "Nie udało się wysłać zdjęć.", true); });
  }

  fileInput.addEventListener("change", function () {
    uploadImages(fileInput.files);
    fileInput.value = "";
  });

  textarea.addEventListener("paste", function (event) {
    var items = (event.clipboardData && event.clipboardData.files) || [];
    if (items.length) { event.preventDefault(); uploadImages(items); }
  });

  textarea.addEventListener("dragover", function (event) {
    if (event.dataTransfer && Array.prototype.indexOf.call(event.dataTransfer.types, "Files") !== -1) {
      event.preventDefault();
      textarea.classList.add("drag-over");
    }
  });
  textarea.addEventListener("dragleave", function () { textarea.classList.remove("drag-over"); });
  textarea.addEventListener("drop", function (event) {
    textarea.classList.remove("drag-over");
    if (event.dataTransfer && event.dataTransfer.files.length) {
      event.preventDefault();
      uploadImages(event.dataTransfer.files);
    }
  });

  // ---------- podgląd ----------
  function togglePreview(show) {
    root.querySelectorAll("[data-action=write],[data-action=preview]").forEach(function (b) {
      b.classList.toggle("editor-tab-active", (b.getAttribute("data-action") === "preview") === show);
    });
    writePane.style.display = show ? "none" : "";
    previewBox.style.display = show ? "" : "none";
    if (!show) { textarea.focus(); return; }

    previewBox.textContent = "Ładowanie podglądu…";
    fetch(previewUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken },
      body: JSON.stringify({ content: textarea.value }),
      credentials: "same-origin"
    })
      .then(function (r) { if (!r.ok) throw new Error(); return r.json(); })
      .then(function (json) {
        // HTML został oczyszczony po stronie serwera (nh3) — ta sama funkcja co na stronie wpisu.
        previewBox.innerHTML = json.html || "<p class=\"muted-info\">Brak treści.</p>";
      })
      .catch(function () { previewBox.textContent = "Nie udało się załadować podglądu."; });
  }
})();
