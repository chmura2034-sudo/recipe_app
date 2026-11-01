/*
 * Wspólne, małe zachowania interfejsu — ładowane z własnej domeny (script-src 'self'),
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
})();
