/*
 * Wspólne, małe zachowania interfejsu - ładowane z własnej domeny (script-src 'self'),
 * dzięki czemu szablony nie potrzebują inline'owych handlerów (onclick=, onsubmit=),
 * których polityka CSP (bez 'unsafe-inline') i tak by nie wykonała.
 *
 *   <form data-confirm="Na pewno?">          -> pyta o potwierdzenie przed wysłaniem
 *   <button data-toggle-target="element-id"> -> pokazuje/ukrywa element o podanym id
 *
 * Teksty pochodzą z atrybutów data-* (dane, nie kod), więc znaki specjalne w nazwach
 * użytkowników czy tytułach przepisów nie mogą wykonać się jako JavaScript.
 */
(function () {
  "use strict";

  document.addEventListener("submit", function (event) {
    var form = event.target;
    var message = form && form.getAttribute && form.getAttribute("data-confirm");
    if (message && !window.confirm(message)) {
      event.preventDefault();
    }
  });

  document.addEventListener("click", function (event) {
    var trigger = event.target.closest && event.target.closest("[data-toggle-target]");
    if (!trigger) return;
    var target = document.getElementById(trigger.getAttribute("data-toggle-target"));
    if (!target) return;
    target.style.display = target.style.display === "none" ? "flex" : "none";
  });

  // ---------- przełącznik motywu: automatyczny (systemowy) -> jasny -> ciemny ----------
  var THEME_ICONS = { auto: "🌓", light: "☀️", dark: "🌙" };
  var THEME_NAMES = { auto: "automatyczny (jak w systemie)", light: "jasny", dark: "ciemny" };
  var themeButton = document.querySelector("[data-theme-toggle]");
  var systemDark = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;

  function storedThemePref() {
    try {
      var value = localStorage.getItem("theme");
      return value === "light" || value === "dark" ? value : "auto";
    } catch (e) { return "auto"; }
  }

  function applyTheme(pref) {
    var dark = pref === "dark" || (pref === "auto" && systemDark && systemDark.matches);
    document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", dark ? "#2a201a" : "#a3461f");
    if (themeButton) {
      var label = "Motyw: " + THEME_NAMES[pref] + " - kliknij, aby zmienić";
      themeButton.textContent = THEME_ICONS[pref];
      themeButton.setAttribute("title", label);
      themeButton.setAttribute("aria-label", label);
    }
  }

  if (themeButton) {
    themeButton.hidden = false;
    applyTheme(storedThemePref());
    themeButton.addEventListener("click", function () {
      var order = ["auto", "light", "dark"];
      var next = order[(order.indexOf(storedThemePref()) + 1) % order.length];
      try {
        if (next === "auto") localStorage.removeItem("theme");
        else localStorage.setItem("theme", next);
      } catch (e) { /* tryb prywatny bez localStorage - motyw działa do odświeżenia */ }
      applyTheme(next);
    });
  }
  if (systemDark && systemDark.addEventListener) {
    // W trybie automatycznym podążamy za zmianą motywu systemu (np. o zmroku).
    systemDark.addEventListener("change", function () {
      if (storedThemePref() === "auto") applyTheme("auto");
    });
  }

  // ---------- „Nie wygaszaj ekranu" (Screen Wake Lock API) ----------
  // Tylko na urządzeniach dotykowych (telefon/tablet), gdzie ekran gaśnie podczas gotowania.
  var wakeButton = document.querySelector("[data-wake-lock]");
  var isTouchDevice = window.matchMedia && window.matchMedia("(pointer: coarse)").matches;
  if (wakeButton && isTouchDevice) {
    var wakeHint = wakeButton.querySelector("[data-wake-lock-hint]");
    var defaultHint = wakeHint.textContent;
    var supported = "wakeLock" in navigator;
    var wakeLock = null;
    var wanted = false;

    var setPressed = function (on) {
      wakeButton.setAttribute("aria-pressed", on ? "true" : "false");
    };

    var requestLock = function () {
      return navigator.wakeLock.request("screen").then(function (lock) {
        wakeLock = lock;
        setPressed(true);
        wakeHint.textContent = defaultHint;
        lock.addEventListener("release", function () {
          wakeLock = null;
          // Przeglądarka zwalnia blokadę po przejściu do innej karty/aplikacji -
          // przycisk zostaje włączony, a blokada wraca po powrocie (visibilitychange).
          if (!wanted) setPressed(false);
        });
      }).catch(function () {
        wanted = false;
        setPressed(false);
        wakeHint.textContent = "Nie udało się włączyć (np. tryb oszczędzania baterii).";
      });
    };

    wakeButton.hidden = false;
    wakeButton.addEventListener("click", function () {
      if (!supported) {
        wakeHint.textContent = window.isSecureContext
          ? "Ta przeglądarka nie obsługuje tej funkcji."
          : "Ta funkcja działa tylko na stronie otwartej przez HTTPS.";
        return;
      }
      wanted = !wanted;
      if (wanted) {
        requestLock();
      } else {
        setPressed(false);
        if (wakeLock) wakeLock.release();
      }
    });

    document.addEventListener("visibilitychange", function () {
      if (wanted && !wakeLock && document.visibilityState === "visible") requestLock();
    });
  }
})();

// ---------- znaczek ♥ na kartach przepisów, które są w ulubionych ----------
(function () {
  "use strict";
  if (!window.RecipeStore) return;
  var favorites = window.RecipeStore.getFavorites();
  document.querySelectorAll(".recipe-card[data-recipe-slug]").forEach(function (card) {
    if (favorites.indexOf(card.getAttribute("data-recipe-slug")) >= 0) card.classList.add("is-favorite");
  });
})();

// ---------- PWA: service worker, przycisk instalacji, informacja o braku sieci ----------
(function () {
  "use strict";
  // Service worker działa tylko w bezpiecznym kontekście (HTTPS albo localhost).
  if ("serviceWorker" in navigator && window.isSecureContext) {
    window.addEventListener("load", function () {
      navigator.serviceWorker.register("/sw.js").catch(function () { /* PWA niedostępne - strona działa normalnie */ });
    });
  }

  var installButton = document.querySelector("[data-install-app]");
  var deferredPrompt = null;
  window.addEventListener("beforeinstallprompt", function (event) {
    event.preventDefault(); // pokażemy własny przycisk zamiast domyślnego paska
    deferredPrompt = event;
    if (installButton) installButton.hidden = false;
  });
  if (installButton) {
    installButton.addEventListener("click", function () {
      if (!deferredPrompt) return;
      deferredPrompt.prompt();
      deferredPrompt.userChoice.finally(function () {
        deferredPrompt = null;
        installButton.hidden = true;
      });
    });
  }
  window.addEventListener("appinstalled", function () {
    if (installButton) installButton.hidden = true;
  });

  // Menu mobilne: lista rozwijana. Przycisk pokazuje tylko CSS na telefonach.
  var navToggle = document.querySelector("[data-nav-toggle]");
  var navLinks = document.getElementById("navLinks");
  function setNavOpen(open) {
    navLinks.classList.toggle("nav-open", open);
    navToggle.setAttribute("aria-expanded", open ? "true" : "false");
  }
  if (navToggle && navLinks) {
    navToggle.addEventListener("click", function () {
      setNavOpen(!navLinks.classList.contains("nav-open"));
    });
    document.addEventListener("click", function (event) {
      if (!event.target.closest("nav") || event.target.closest("#navLinks a")) setNavOpen(false);
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && navLinks.classList.contains("nav-open")) {
        setNavOpen(false);
        navToggle.focus();
      }
    });
    // Powrót przyciskiem „wstecz” może przywrócić stronę z pamięci z otwartym menu.
    window.addEventListener("pageshow", function (event) {
      if (event.persisted) setNavOpen(false);
    });
  }

  var banner = document.querySelector("[data-offline-banner]");
  function updateOnline() {
    if (banner) banner.hidden = navigator.onLine;
  }
  window.addEventListener("online", updateOnline);
  window.addEventListener("offline", updateOnline);
  updateOnline();
})();
