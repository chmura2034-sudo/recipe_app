/*
 * Funkcje strony przepisu: dodawanie do listy zakupów (pkt 2), ulubione, minutniki w krokach.
 * Wymaga static/js/shopping-store.js (window.RecipeStore).
 */
(function () {
  "use strict";
  var store = window.RecipeStore;
  if (!store) return;

  // ---------- lista zakupów ----------
  var addButton = document.querySelector("[data-add-to-shopping]");
  var feedback = document.querySelector("[data-shopping-feedback]");
  if (addButton) {
    addButton.hidden = false;
    addButton.addEventListener("click", function () {
      var items = [];
      document.querySelectorAll("#ingredientsList li[data-ingredient-name]").forEach(function (li) {
        var amountEl = li.querySelector(".amount-value");
        items.push({
          // Bieżąca, wyświetlana ilość - czyli po ewentualnym przeliczeniu porcji/formy.
          amount: amountEl ? amountEl.textContent.trim() : "",
          unit: li.getAttribute("data-ingredient-unit") || "",
          name: li.getAttribute("data-ingredient-name") || "",
        });
      });
      var servingsEl = document.getElementById("servingsValue");
      var existed = store.addRecipeToShopping({
        slug: addButton.getAttribute("data-recipe-slug"),
        title: addButton.getAttribute("data-recipe-title"),
        url: addButton.getAttribute("data-recipe-url"),
        servings: servingsEl ? servingsEl.textContent.trim() : "",
        items: items,
      });
      if (feedback) {
        feedback.textContent = existed
          ? "Zaktualizowano składniki tego przepisu na liście zakupów."
          : "Dodano składniki do listy zakupów.";
        var link = document.createElement("a");
        link.href = "/lista-zakupow";
        link.textContent = " Zobacz listę →";
        feedback.appendChild(link);
      }
    });
  }
})();

// ---------- ulubione ----------
(function () {
  "use strict";
  var store = window.RecipeStore;
  if (!store) return;

  var toggle = document.querySelector("[data-favorite-toggle]");
  if (toggle) {
    var slug = toggle.getAttribute("data-recipe-slug");
    var update = function (on) {
      toggle.textContent = on ? "♥" : "♡";
      toggle.classList.toggle("is-favorite", on);
      toggle.setAttribute("aria-pressed", on ? "true" : "false");
      var label = on ? "Usuń z ulubionych" : "Dodaj do ulubionych";
      toggle.title = label;
      toggle.setAttribute("aria-label", label);
    };
    toggle.hidden = false;
    update(store.isFavorite(slug));
    toggle.addEventListener("click", function () { update(store.toggleFavorite(slug)); });
  }
})();

// ---------- minutniki w krokach przepisu ----------
// Krok typu „piecz 40 minut" / „gotuj 1,5 godziny" / „odstaw na pół godziny" dostaje przycisk ⏱.
(function () {
  "use strict";
  var steps = document.querySelectorAll("#stepsChecklist li");
  if (!steps.length) return;

  var DURATION_RE = /(\d+(?:[.,]\d+)?)(?:\s*[-–]\s*\d+(?:[.,]\d+)?)?\s*(godzin\w*|godz\.?|h\b|minut\w*|min\b\.?|sekund\w*|sek\b\.?|s\b)|(pół\s+godziny|półtorej\s+godziny|kwadrans\w*)/gi;
  var originalTitle = document.title;
  var audioCtx = null;

  function toSeconds(match) {
    if (match[3]) {
      var phrase = match[3].toLowerCase();
      if (phrase.indexOf("półtorej") === 0) return 90 * 60;
      if (phrase.indexOf("pół") === 0) return 30 * 60;
      return 15 * 60; // kwadrans
    }
    var value = parseFloat(match[1].replace(",", "."));
    var unit = match[2].toLowerCase();
    if (unit[0] === "g" || unit === "h") return Math.round(value * 3600);
    if (unit[0] === "m") return Math.round(value * 60);
    return Math.round(value);
  }

  function label(seconds) {
    if (seconds >= 3600) {
      var h = Math.floor(seconds / 3600), m = Math.round((seconds % 3600) / 60);
      return h + " h" + (m ? " " + m + " min" : "");
    }
    if (seconds >= 60) return Math.round(seconds / 60) + " min";
    return seconds + " s";
  }

  function clock(seconds) {
    var h = Math.floor(seconds / 3600), m = Math.floor((seconds % 3600) / 60), s = seconds % 60;
    var mm = (h ? String(m).padStart(2, "0") : String(m)) + ":" + String(s).padStart(2, "0");
    return h ? h + ":" + mm : mm;
  }

  function beep() {
    try {
      audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
      [0, 0.4, 0.8].forEach(function (offset) {
        var osc = audioCtx.createOscillator();
        var gain = audioCtx.createGain();
        osc.frequency.value = 880;
        gain.gain.setValueAtTime(0.25, audioCtx.currentTime + offset);
        gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + offset + 0.3);
        osc.connect(gain).connect(audioCtx.destination);
        osc.start(audioCtx.currentTime + offset);
        osc.stop(audioCtx.currentTime + offset + 0.3);
      });
    } catch (e) { /* brak Web Audio - zostaje sygnał wizualny */ }
    if (navigator.vibrate) navigator.vibrate([300, 150, 300, 150, 300]);
  }

  function createTimer(seconds, stepNumber) {
    var wrap = document.createElement("span");
    wrap.className = "step-timer";
    var button = document.createElement("button");
    button.type = "button";
    button.className = "step-timer-btn";
    var reset = document.createElement("button");
    reset.type = "button";
    reset.className = "step-timer-reset";
    reset.textContent = "↺";
    reset.title = "Zresetuj minutnik";
    reset.setAttribute("aria-label", "Zresetuj minutnik");
    reset.hidden = true;
    wrap.append(button, reset);

    var state = "idle"; // idle | running | paused | done
    var remaining = seconds;
    var endAt = 0;
    var interval = null;

    function render() {
      wrap.className = "step-timer step-timer-" + state;
      if (state === "idle") button.textContent = "⏱ " + label(seconds);
      else if (state === "running") button.textContent = "⏸ " + clock(remaining);
      else if (state === "paused") button.textContent = "▶ " + clock(remaining);
      else button.textContent = "✓ Gotowe!";
      button.setAttribute("aria-label", state === "idle"
        ? "Uruchom minutnik " + label(seconds) + " (krok " + stepNumber + ")"
        : button.textContent);
      reset.hidden = state === "idle";
    }

    function tick() {
      // Liczymy od czasu zakończenia, a nie liczbą „ticków" - przeglądarka spowalnia
      // timery w kartach w tle, a minutnik ma i tak skończyć się o czasie.
      remaining = Math.max(0, Math.round((endAt - Date.now()) / 1000));
      if (remaining === 0) {
        clearInterval(interval);
        state = "done";
        beep();
        document.title = "⏰ Krok " + stepNumber + " - gotowe!";
        setTimeout(function () { document.title = originalTitle; }, 10000);
      }
      render();
    }

    button.addEventListener("click", function () {
      if (audioCtx === null) {
        // Odblokowanie dźwięku wymaga gestu użytkownika - robimy to przy pierwszym kliknięciu.
        try { audioCtx = new (window.AudioContext || window.webkitAudioContext)(); } catch (e) { audioCtx = false; }
      }
      if (state === "running") {
        clearInterval(interval);
        state = "paused";
      } else if (state === "done") {
        state = "idle";
        remaining = seconds;
      } else {
        endAt = Date.now() + remaining * 1000;
        state = "running";
        interval = setInterval(tick, 250);
      }
      render();
    });
    reset.addEventListener("click", function () {
      clearInterval(interval);
      state = "idle";
      remaining = seconds;
      document.title = originalTitle;
      render();
    });
    render();
    return wrap;
  }

  steps.forEach(function (li, index) {
    var textEl = li.querySelector(".step-check-text");
    if (!textEl) return;
    var text = textEl.textContent;
    var seen = {};
    var timers = [];
    var match;
    DURATION_RE.lastIndex = 0;
    while ((match = DURATION_RE.exec(text)) && timers.length < 3) {
      var seconds = toSeconds(match);
      if (seconds < 10 || seconds > 48 * 3600 || seen[seconds]) continue;
      seen[seconds] = true;
      timers.push(createTimer(seconds, index + 1));
    }
    if (timers.length) {
      var box = document.createElement("div");
      box.className = "step-timers";
      timers.forEach(function (t) { box.appendChild(t); });
      li.appendChild(box);
    }
  });
})();
