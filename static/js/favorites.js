/* Strona „Ulubione": pobiera dane kart z /api/przepisy dla slugów zapisanych w przeglądarce. */
(function () {
  "use strict";
  var store = window.RecipeStore;
  var grid = document.querySelector("[data-favorites-grid]");
  var empty = document.querySelector("[data-favorites-empty]");
  if (!store || !grid) return;

  var slugs = store.getFavorites();
  if (!slugs.length) { empty.hidden = false; return; }

  fetch("/api/przepisy?slugi=" + encodeURIComponent(slugs.join(",")), { credentials: "same-origin" })
    .then(function (r) { return r.json(); })
    .then(function (data) {
      var bySlug = {};
      data.recipes.forEach(function (r) { bySlug[r.slug] = r; });
      var shown = slugs.filter(function (s) { return bySlug[s]; });
      if (!shown.length) { empty.hidden = false; return; }
      shown.forEach(function (slug) {
        var r = bySlug[slug];
        var card = document.createElement("a");
        card.className = "recipe-card";
        card.href = r.url;
        if (r.image_url) {
          var img = document.createElement("img");
          img.src = r.image_url;
          img.alt = r.title;
          card.appendChild(img);
        } else {
          var ph = document.createElement("div");
          ph.className = "recipe-card-placeholder";
          ph.textContent = "🍽️";
          card.appendChild(ph);
        }
        var body = document.createElement("div");
        body.className = "recipe-card-body";
        var h = document.createElement("h2");
        h.textContent = r.title;
        body.appendChild(h);
        if (r.description) {
          var p = document.createElement("p");
          p.textContent = r.description;
          body.appendChild(p);
        }
        var meta = document.createElement("div");
        meta.className = "recipe-meta";
        if (r.rating) {
          var rating = document.createElement("span");
          rating.className = "rating-badge";
          rating.textContent = "★ " + r.rating;
          meta.appendChild(rating);
        }
        if (r.prep_time) {
          var time = document.createElement("span");
          time.textContent = "⏱ " + r.prep_time;
          meta.appendChild(time);
        }
        body.appendChild(meta);
        card.appendChild(body);
        grid.appendChild(card);
      });
    })
    .catch(function () {
      empty.hidden = false;
      empty.textContent = "Nie udało się wczytać ulubionych (brak połączenia?).";
    });
})();
