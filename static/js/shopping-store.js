/*
 * Wspólny magazyn listy zakupów i ulubionych — wszystko w localStorage przeglądarki
 * (czytelnicy nie mają kont, a lista działa też offline). Udostępnia window.RecipeStore.
 */
(function () {
  "use strict";

  var SHOPPING_KEY = "shopping-list-v1";
  var FAVORITES_KEY = "favorites-v1";

  function read(key, fallback) {
    try {
      var value = JSON.parse(localStorage.getItem(key) || "null");
      return value === null ? fallback : value;
    } catch (e) {
      return fallback;
    }
  }

  function write(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
      return true;
    } catch (e) {
      return false; // tryb prywatny / brak miejsca
    }
  }

  function getShopping() {
    var data = read(SHOPPING_KEY, null);
    if (!data || !Array.isArray(data.recipes)) data = { recipes: [], checked: [] };
    if (!Array.isArray(data.checked)) data.checked = [];
    return data;
  }

  /** Dodaje przepis do listy; ponowne dodanie tego samego przepisu podmienia jego składniki
   *  (np. po przeliczeniu na inną liczbę porcji). Zwraca true, jeśli przepis już był. */
  function addRecipeToShopping(recipe) {
    var data = getShopping();
    var existed = false;
    data.recipes = data.recipes.filter(function (r) {
      if (r.slug === recipe.slug) { existed = true; return false; }
      return true;
    });
    data.recipes.push(recipe);
    write(SHOPPING_KEY, data);
    return existed;
  }

  function getFavorites() {
    var list = read(FAVORITES_KEY, []);
    return Array.isArray(list) ? list.filter(function (s) { return typeof s === "string"; }) : [];
  }

  function toggleFavorite(slug) {
    var list = getFavorites();
    var index = list.indexOf(slug);
    if (index >= 0) list.splice(index, 1);
    else list.unshift(slug);
    write(FAVORITES_KEY, list);
    return index < 0; // true = teraz jest w ulubionych
  }

  window.RecipeStore = {
    getShopping: getShopping,
    saveShopping: function (data) { return write(SHOPPING_KEY, data); },
    addRecipeToShopping: addRecipeToShopping,
    getFavorites: getFavorites,
    toggleFavorite: toggleFavorite,
    isFavorite: function (slug) { return getFavorites().indexOf(slug) >= 0; },
  };
})();
