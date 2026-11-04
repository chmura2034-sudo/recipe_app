# Graph Report - recipe_app  (2026-11-04)

## Corpus Check
- 24 files · ~34,041 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 14 file(s) not represented in the graph (top: .example 6, (none) 5, .ini 1)

## Summary
- 461 nodes · 826 edges · 38 communities (28 shown, 10 thin omitted)
- Extraction: 92% EXTRACTED · 8% INFERRED · 0% AMBIGUOUS · INFERRED: 66 edges (avg confidence: 0.89)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `82f3ea22`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- create_app
- Recipe
- README Docs & Security
- User
- resetScale
- Alembic Migrations
- Tag
- serialize_ingredient_entries
- Configuration
- sqlalchemy
- Access Decorators
- models.py
- Logo Branding
- SQLite Pragmas
- blog_editor.js
- _fold
- recipe_detail
- recipe.js
- _save_recipe_form
- shopping-store.js
- RecipeRating
- _save_blog_form
- _sanitize_and_save_image
- shopping.js
- sw.js
- _build_backup_zip
- _referenced_image_names
- index
- animation_save_options
- sitemap_xml
- _read_password
- admin_stats
- form_count

## God Nodes (most connected - your core abstractions)
1. `create_app()` - 126 edges
2. `Recipe` - 33 edges
3. `Wielka Księga Przepisów README` - 25 edges
4. `User` - 21 edges
5. `_save_recipe_form()` - 15 edges
6. `Recipe create/edit form` - 15 edges
7. `BlogPost` - 14 edges
8. `Base layout template` - 14 edges
9. `Recipe detail page` - 14 edges
10. `recipe_detail()` - 13 edges

## Surprising Connections (you probably didn't know these)
- `ingredients_structured JSON serializer (submit handler)` --shares_data_with--> `serialize_ingredient_entries()`  [INFERRED]
  templates/admin/recipe_form.html → app.py
- `index()` --references--> `Public recipe list page`  [INFERRED]
  app.py → templates/index.html
- `recipe_detail()` --references--> `Recipe detail page`  [INFERRED]
  app.py → templates/recipe_detail.html
- `redaktor_dashboard()` --references--> `Redaktor (editor) dashboard`  [INFERRED]
  app.py → templates/redaktor/dashboard.html
- `backup_page()` --references--> `Backup export/import page`  [INFERRED]
  app.py → templates/admin/backup.html

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Built-in security measures** — readme_sql_injection_protection, readme_xss_csp_protection, readme_safe_redirect, readme_timing_attack_protection, readme_logout_post_only, readme_proxy_count, readme_zip_bomb_protection, readme_strong_passwords, readme_image_sanitization, readme_login_rate_limiting, readme_csrf_protection [EXTRACTED 1.00]
- **Client-side recipe scaling (servings/pan area) incl. nutrition** — templates_recipe_detail_scale_panel, templates_recipe_detail_applyscale, templates_recipe_detail_areafor, templates_recipe_detail_updatenutrition, templates_recipe_detail_resetscale, templates_recipe_detail_nutrition_summary [EXTRACTED 1.00]
- **Recipe approval workflow (editor submits, admin approves/rejects)** — templates_redaktor_dashboard, templates_admin_recipe_form, templates_admin_queue, templates_admin_queue_reject_form, readme_approval_queue, app_create_app_recipe_approve, app_create_app_recipe_reject [INFERRED 0.85]

## Communities (38 total, 10 thin omitted)

### Community 0 - "create_app"
Cohesion: 0.08
Nodes (3): create_app(), _csp_nonce(), inject_csp_nonce()

### Community 1 - "Recipe"
Cohesion: 0.08
Nodes (4): Recipe, Public recipe list page, Recipe title search form, Tag filter chips

### Community 2 - "README Docs & Security"
Cohesion: 0.06
Nodes (27): change_own_password(), comment_delete(), login(), logout(), _post_login_redirect_endpoint(), redaktor_dashboard(), is_safe_redirect_target(), Wielka Księga Przepisów README (+19 more)

### Community 3 - "User"
Cohesion: 0.08
Nodes (17): admin_dashboard(), backup_page(), blog_reject(), editor_create(), editor_delete(), editor_reset_password(), editors_page(), recipe_reject() (+9 more)

### Community 5 - "resetScale"
Cohesion: 0.21
Nodes (10): updatePanFields(), applyScale(), areaFor(), formatNumber(), Nutrition summary (total / per serving), panDimensionsText(), resetScale(), Recipe scale panel (servings / pan) (+2 more)

### Community 6 - "Alembic Migrations"
Cohesion: 0.23
Nodes (5): get_engine(), get_engine_url(), get_metadata(), run_migrations_offline(), run_migrations_online()

### Community 7 - "Tag"
Cohesion: 0.21
Nodes (11): _backup_count(), backup_import(), _parse_backup_datetime(), _restore_blog_post_from_backup(), _restore_previous_image(), _restore_reader_data(), _restore_recipe_from_backup(), Tag (+3 more)

### Community 8 - "serialize_ingredient_entries"
Cohesion: 0.29
Nodes (4): _clean_line_field(), _clean_number_field(), is_negative_text(), serialize_ingredient_entries()

### Community 9 - "Configuration"
Cohesion: 0.14
Nodes (5): Config, DevelopmentConfig, get_config(), TestingConfig, validate_production_config()

### Community 10 - "sqlalchemy"
Cohesion: 0.09
Nodes (11): upgrade(), upgrade(), upgrade(), upgrade(), _slugify(), upgrade(), upgrade(), upgrade() (+3 more)

### Community 11 - "Access Decorators"
Cohesion: 0.33
Nodes (3): admin_required(), wrapped(), redaktor_or_admin_required()

### Community 12 - "models.py"
Cohesion: 0.07
Nodes (7): blog_preview(), _blog_attribute_filter(), blog_markdown_to_plain_text(), BlogPost, Comment, RecipeRating, render_blog_markdown()

### Community 13 - "Logo Branding"
Cohesion: 0.50
Nodes (5): Young Chef in White Double-Breasted Jacket, Cooking / Recipe Preparation Theme, Red-Tinted Hand-Drawn Line-Art Style, Circular Crop, Recipe App Logo (Chef Illustration), Large Steel Mixing Bowl with Red Sauce Being Whisked

### Community 15 - "blog_editor.js"
Cohesion: 0.42
Nodes (7): insertBlock(), prefixLines(), replaceSelection(), selectedText(), setStatus(), uploadImages(), wrap()

### Community 16 - "_fold"
Cohesion: 0.20
Nodes (7): _fold(), _ingredient_matches(), match_recipe_ingredients(), is_basic(), parse_ingredient_terms(), _same_stem(), _stem()

### Community 18 - "recipe_detail"
Cohesion: 0.16
Nodes (11): api_recipes_by_slug(), blog_detail(), _comment_form_context(), _count_view(), _published_comments(), _rating_stats(), recipe_detail(), _recipe_jsonld() (+3 more)

### Community 19 - "recipe.js"
Cohesion: 0.39
Nodes (6): beep(), clock(), createTimer(), render(), tick(), label()

### Community 20 - "_save_recipe_form"
Cohesion: 0.09
Nodes (29): blog_delete(), _build_instructions_text(), _delete_views(), _hold_approved_image(), _ingredient_entries_from_form(), _queue_image_cleanup(), recipe_create(), recipe_delete() (+21 more)

### Community 21 - "shopping-store.js"
Cohesion: 0.57
Nodes (6): addRecipeToShopping(), getFavorites(), getShopping(), read(), toggleFavorite(), write()

### Community 22 - "RecipeRating"
Cohesion: 0.33
Nodes (7): blog_comment(), _form_ts_elapsed(), _handle_comment_post(), _hmac_hex(), recipe_comment(), recipe_rate(), _voter_hash_from_cookie()

### Community 23 - "_save_blog_form"
Cohesion: 0.31
Nodes (9): _approve_changes(), blog_approve(), blog_create(), blog_edit(), recipe_approve(), redaktor_blog_create(), redaktor_blog_edit(), _render_blog_form() (+1 more)

### Community 24 - "_sanitize_and_save_image"
Cohesion: 0.50
Nodes (4): blog_upload_images(), _extract_backup_images(), _sanitize_and_save_image(), _save_uploaded_image()

### Community 25 - "shopping.js"
Cohesion: 0.60
Nodes (5): aggregate(), amountText(), formatNumber(), parseAmount(), render()

### Community 26 - "sw.js"
Cohesion: 0.47
Nodes (4): handleImage(), handlePage(), PRECACHE, trimCache()

### Community 27 - "_build_backup_zip"
Cohesion: 0.40
Nodes (4): backup_export(), _build_backup_zip(), export_backup(), _export_reader_data()

### Community 28 - "_referenced_image_names"
Cohesion: 0.67
Nodes (4): cleanup_images(), _referenced_image_names(), _remove_image_files(), remove_unused_images()

### Community 29 - "index"
Cohesion: 0.40
Nodes (3): index(), _escape_like(), fold_search_text()

### Community 35 - "_read_password"
Cohesion: 0.67
Nodes (4): create_admin(), create_redaktor(), _read_password(), _upsert_user()

## Knowledge Gaps
- **11 isolated node(s):** `Recipe title search form`, `Tag filter chips`, `Cooking / Recipe Preparation Theme`, `Red-Tinted Hand-Drawn Line-Art Style, Circular Crop`, `Flash messages block` (+6 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 175 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **10 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `create_app()` connect `create_app` to `Recipe`, `README Docs & Security`, `User`, `App Imports`, `Tag`, `Configuration`, `models.py`, `SQLite Pragmas`, `recipe_detail`, `_save_recipe_form`, `RecipeRating`, `_save_blog_form`, `_sanitize_and_save_image`, `_build_backup_zip`, `_referenced_image_names`, `index`, `wsgi.py`, `sitemap_xml`, `_read_password`, `admin_stats`?**
  _High betweenness centrality (0.368) - this node is a cross-community bridge._
- **Are the 9 inferred relationships involving `Recipe` (e.g. with `serialize_ingredient_entries()` and `Recipe approval queue (/admin/kolejka)`) actually correct?**
  _`Recipe` has 9 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Recipe title search form`, `Tag filter chips`, `Cooking / Recipe Preparation Theme` to the rest of the system?**
  _11 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `create_app` be split into smaller, more focused modules?**
  _Cohesion score 0.07692307692307693 - nodes in this community are weakly interconnected._
- **Why does `Recipe` connect `Recipe` to `create_app`, `README Docs & Security`, `User`, `App Imports`, `Tag`, `serialize_ingredient_entries`, `models.py`, `_save_recipe_form`?**
  _High betweenness centrality (0.160) - this node is a cross-community bridge._
- **Are the 3 inferred relationships involving `User` (e.g. with `Redaktor (editor) role` and `Admin dashboard template`) actually correct?**
  _`User` has 3 INFERRED edges - model-reasoned connections that need verification._
- **Should `Recipe` be split into smaller, more focused modules?**
  _Cohesion score 0.0812807881773399 - nodes in this community are weakly interconnected._