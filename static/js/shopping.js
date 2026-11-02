/*
 * Strona listy zakupów: sumuje składniki ze wszystkich dodanych przepisów
 * (ta sama nazwa + jednostka -> jedna pozycja), pozwala odhaczać kupione i kopiować listę.
 * Wszystkie teksty wstawiane przez textContent - nazwy składników nie wykonają się jako HTML.
 */
(function () {
  "use strict";
  var store = window.RecipeStore;
  var app = document.getElementById("shoppingApp");
  if (!store || !app) return;
  app.hidden = false;

  var emptyEl = app.querySelector("[data-shopping-empty]");
  var contentEl = app.querySelector("[data-shopping-content]");
  var itemsEl = app.querySelector("[data-shopping-items]");
  var recipesEl = app.querySelector("[data-shopping-recipes]");
  var copyStatus = app.querySelector("[data-shopping-copy-status]");

  function parseAmount(value) {
    var n = parseFloat(String(value || "").replace(",", "."));
    return isNaN(n) ? null : n;
  }

  function formatNumber(n) {
    var rounded = Math.round(n * 100) / 100;
    return String(rounded).replace(".", ",");
  }

  /** Łączy składniki wszystkich przepisów w pozycje listy. */
  function aggregate(data) {
    var map = {};
    var order = [];
    data.recipes.forEach(function (recipe) {
      (recipe.items || []).forEach(function (item) {
        var name = String(item.name || "").trim();
        if (!name) return;
        var unit = String(item.unit || "").trim();
        var key = name.toLowerCase() + "|" + unit.toLowerCase();
        if (!map[key]) {
          map[key] = { key: key, name: name, unit: unit, total: 0, hasNumber: false, extras: [], sources: [] };
          order.push(key);
        }
        var entry = map[key];
        var amount = parseAmount(item.amount);
        if (amount !== null) {
          entry.total += amount;
          entry.hasNumber = true;
        } else if (item.amount) {
          entry.extras.push(String(item.amount)); // np. "do smaku", "szczypta"
        }
        if (entry.sources.indexOf(recipe.title) < 0) entry.sources.push(recipe.title);
      });
    });
    return order.map(function (k) { return map[k]; });
  }

  function amountText(entry) {
    var parts = [];
    if (entry.hasNumber) parts.push(formatNumber(entry.total) + (entry.unit ? " " + entry.unit : ""));
    else if (entry.unit && !entry.extras.length) parts.push(entry.unit);
    entry.extras.forEach(function (e) { if (parts.indexOf(e) < 0) parts.push(e); });
    return parts.join(" + ");
  }

  function render() {
    var data = store.getShopping();
    var entries = aggregate(data);
    // Usuwamy znaczniki "kupione" dla pozycji, których już nie ma.
    var keys = entries.map(function (e) { return e.key; });
    data.checked = data.checked.filter(function (k) { return keys.indexOf(k) >= 0; });

    emptyEl.hidden = entries.length > 0;
    contentEl.hidden = entries.length === 0;
    itemsEl.textContent = "";
    recipesEl.textContent = "";

    // Najpierw do kupienia, potem kupione.
    entries.sort(function (a, b) {
      return (data.checked.indexOf(a.key) >= 0) - (data.checked.indexOf(b.key) >= 0);
    });

    entries.forEach(function (entry) {
      var checked = data.checked.indexOf(entry.key) >= 0;
      var li = document.createElement("li");
      li.className = "shopping-item" + (checked ? " shopping-item-done" : "");
      var label = document.createElement("label");
      var box = document.createElement("input");
      box.type = "checkbox";
      box.checked = checked;
      box.addEventListener("change", function () {
        var d = store.getShopping();
        d.checked = d.checked.filter(function (k) { return k !== entry.key; });
        if (box.checked) d.checked.push(entry.key);
        store.saveShopping(d);
        render();
      });
      var amount = document.createElement("strong");
      amount.className = "shopping-amount";
      amount.textContent = amountText(entry);
      var name = document.createElement("span");
      name.textContent = entry.name;
      var src = document.createElement("small");
      src.className = "shopping-source";
      src.textContent = entry.sources.join(", ");
      label.append(box, amount, name, src);
      li.appendChild(label);
      itemsEl.appendChild(li);
    });

    data.recipes.forEach(function (recipe) {
      var li = document.createElement("li");
      var link = document.createElement("a");
      link.href = recipe.url || "#";
      link.textContent = recipe.title;
      li.appendChild(link);
      if (recipe.servings) {
        var info = document.createElement("small");
        info.textContent = " (" + recipe.servings + " porcji)";
        li.appendChild(info);
      }
      var remove = document.createElement("button");
      remove.type = "button";
      remove.className = "nav-link-button shopping-remove";
      remove.textContent = "Usuń";
      remove.addEventListener("click", function () {
        var d = store.getShopping();
        d.recipes = d.recipes.filter(function (r) { return r.slug !== recipe.slug; });
        store.saveShopping(d);
        render();
      });
      li.appendChild(remove);
      recipesEl.appendChild(li);
    });

    store.saveShopping(data);
  }

  app.querySelector("[data-shopping-clear-checked]").addEventListener("click", function () {
    // "Usuń kupione" - odhaczone pozycje znikają z listy, ale przepisy zostają.
    var d = store.getShopping();
    d.recipes.forEach(function (recipe) {
      recipe.items = (recipe.items || []).filter(function (item) {
        var key = String(item.name || "").trim().toLowerCase() + "|" + String(item.unit || "").trim().toLowerCase();
        return d.checked.indexOf(key) < 0;
      });
    });
    d.recipes = d.recipes.filter(function (r) { return r.items.length; });
    d.checked = [];
    store.saveShopping(d);
    render();
  });

  app.querySelector("[data-shopping-clear-all]").addEventListener("click", function () {
    if (!window.confirm("Wyczyścić całą listę zakupów?")) return;
    store.saveShopping({ recipes: [], checked: [] });
    render();
  });

  app.querySelector("[data-shopping-copy]").addEventListener("click", function () {
    var data = store.getShopping();
    var lines = aggregate(data)
      .filter(function (e) { return data.checked.indexOf(e.key) < 0; })
      .map(function (e) { var a = amountText(e); return "☐ " + (a ? a + " " : "") + e.name; });
    var text = "Lista zakupów:\n" + lines.join("\n");
    var done = function () { copyStatus.textContent = "Skopiowano do schowka."; };
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(done, function () { copyStatus.textContent = "Nie udało się skopiować."; });
    } else {
      var area = document.createElement("textarea");
      area.value = text;
      document.body.appendChild(area);
      area.select();
      try { document.execCommand("copy"); done(); } catch (e) { copyStatus.textContent = "Nie udało się skopiować."; }
      area.remove();
    }
  });

  // Zmiany z innej karty (np. dodanie przepisu) odświeżają listę.
  window.addEventListener("storage", render);
  render();
})();
