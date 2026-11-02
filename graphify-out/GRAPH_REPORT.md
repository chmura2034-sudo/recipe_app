# Graph Report - recipe_app  (2026-11-02)

## Corpus Check
- 18 files · ~29,013 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 12 file(s) not represented in the graph (top: .example 5, (none) 4, .ini 1)

## Summary
- 394 nodes · 666 edges · 34 communities (25 shown, 9 thin omitted)
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 65 edges (avg confidence: 0.89)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `ef0f0a76`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- create_app
- Recipe create/edit form
- README Docs & Security
- Users & Editor Accounts
- Recipe Model Logic
- Alembic Migrations
- Backup export/import page
- Recipe Scaling & Nutrition
- Configuration
- sqlalchemy
- Access Decorators
- models.py
- Logo Branding
- SQLite Pragmas
- blog_editor.js
- recipe_detail
- recipe.js
- Base layout template
- shopping-store.js
- _handle_comment_post
- _save_blog_form
- _fold
- shopping.js
- sw.js
- _build_backup_zip
- _sanitize_and_save_image
- parse_ingredient_terms
- admin_stats
- sitemap_xml

## God Nodes (most connected - your core abstractions)
1. `create_app()` - 108 edges
2. `Recipe` - 31 edges
3. `Wielka Księga Przepisów README` - 25 edges
4. `User` - 20 edges
5. `Recipe create/edit form` - 15 edges
6. `Base layout template` - 14 edges
7. `Recipe detail page` - 14 edges
8. `recipe_detail()` - 13 edges
9. `BlogPost` - 13 edges
10. `Tag` - 12 edges

## Surprising Connections (you probably didn't know these)
- `recipe_detail()` --references--> `Recipe detail page`  [INFERRED]
  app.py → templates/recipe_detail.html
- `login()` --references--> `Login page template`  [INFERRED]
  app.py → templates/login.html
- `recipe_edit()` --references--> `Recipe create/edit form`  [INFERRED]
  app.py → templates/admin/recipe_form.html
- `redaktor_recipe_create()` --references--> `Recipe create/edit form`  [INFERRED]
  app.py → templates/admin/recipe_form.html
- `backup_page()` --references--> `Backup export/import page`  [INFERRED]
  app.py → templates/admin/backup.html

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Built-in security measures** — readme_sql_injection_protection, readme_xss_csp_protection, readme_safe_redirect, readme_timing_attack_protection, readme_logout_post_only, readme_proxy_count, readme_zip_bomb_protection, readme_strong_passwords, readme_image_sanitization, readme_login_rate_limiting, readme_csrf_protection [EXTRACTED 1.00]
- **Client-side recipe scaling (servings/pan area) incl. nutrition** — templates_recipe_detail_scale_panel, templates_recipe_detail_applyscale, templates_recipe_detail_areafor, templates_recipe_detail_updatenutrition, templates_recipe_detail_resetscale, templates_recipe_detail_nutrition_summary [EXTRACTED 1.00]
- **Recipe approval workflow (editor submits, admin approves/rejects)** — templates_redaktor_dashboard, templates_admin_recipe_form, templates_admin_queue, templates_admin_queue_reject_form, readme_approval_queue, app_create_app_recipe_approve, app_create_app_recipe_reject [INFERRED 0.85]

## Communities (34 total, 9 thin omitted)

### Community 0 - "create_app"
Cohesion: 0.07
Nodes (3): create_app(), _csp_nonce(), inject_csp_nonce()

### Community 1 - "Recipe create/edit form"
Cohesion: 0.09
Nodes (24): _clean_line_field(), backup_import(), _build_ingredients_text(), _build_instructions_text(), recipe_create(), redaktor_recipe_edit(), _restore_blog_post_from_backup(), _restore_recipe_from_backup() (+16 more)

### Community 2 - "README Docs & Security"
Cohesion: 0.09
Nodes (16): Wielka Księga Przepisów README, Environment variables (.env, APP_ENV, SECRET_KEY...), Production deployment (Docker or gunicorn+nginx+systemd), requirements.txt dependencies, Flask, Flask-Limiter, Flask-Login, Flask-Migrate (+8 more)

### Community 3 - "Users & Editor Accounts"
Cohesion: 0.10
Nodes (12): create_admin(), create_redaktor(), editor_create(), editor_delete(), editor_reset_password(), editors_page(), _read_password(), _upsert_user() (+4 more)

### Community 5 - "Recipe Model Logic"
Cohesion: 0.09
Nodes (5): redaktor_dashboard(), redaktor_recipe_create(), redaktor_recipe_delete(), Recipe, Redaktor (editor) dashboard

### Community 6 - "Alembic Migrations"
Cohesion: 0.23
Nodes (5): get_engine(), get_engine_url(), get_metadata(), run_migrations_offline(), run_migrations_online()

### Community 7 - "Backup export/import page"
Cohesion: 0.20
Nodes (4): _parse_backup_datetime(), _restore_reader_data(), Comment, RecipeRating

### Community 8 - "Recipe Scaling & Nutrition"
Cohesion: 0.18
Nodes (10): Recipe detail page, applyScale(), areaFor(), formatNumber(), Nutrition summary (total / per serving), panDimensionsText(), resetScale(), Recipe scale panel (servings / pan) (+2 more)

### Community 9 - "Configuration"
Cohesion: 0.15
Nodes (5): Config, DevelopmentConfig, get_config(), TestingConfig, validate_production_config()

### Community 10 - "sqlalchemy"
Cohesion: 0.22
Nodes (4): upgrade(), upgrade(), upgrade(), upgrade()

### Community 11 - "Access Decorators"
Cohesion: 0.33
Nodes (3): admin_required(), wrapped(), redaktor_or_admin_required()

### Community 12 - "models.py"
Cohesion: 0.11
Nodes (5): blog_preview(), _blog_attribute_filter(), blog_markdown_to_plain_text(), BlogPost, render_blog_markdown()

### Community 13 - "Logo Branding"
Cohesion: 0.50
Nodes (5): Young Chef in White Double-Breasted Jacket, Cooking / Recipe Preparation Theme, Red-Tinted Hand-Drawn Line-Art Style, Circular Crop, Recipe App Logo (Chef Illustration), Large Steel Mixing Bowl with Red Sauce Being Whisked

### Community 15 - "blog_editor.js"
Cohesion: 0.42
Nodes (7): insertBlock(), prefixLines(), replaceSelection(), selectedText(), setStatus(), uploadImages(), wrap()

### Community 18 - "recipe_detail"
Cohesion: 0.20
Nodes (10): api_recipes_by_slug(), blog_detail(), _comment_form_context(), _count_view(), _published_comments(), _rating_stats(), recipe_detail(), _recipe_jsonld() (+2 more)

### Community 19 - "recipe.js"
Cohesion: 0.39
Nodes (6): beep(), clock(), createTimer(), render(), tick(), label()

### Community 20 - "Base layout template"
Cohesion: 0.09
Nodes (25): admin_dashboard(), backup_page(), change_own_password(), comment_delete(), index(), login(), logout(), _post_login_redirect_endpoint() (+17 more)

### Community 21 - "shopping-store.js"
Cohesion: 0.57
Nodes (6): addRecipeToShopping(), getFavorites(), getShopping(), read(), toggleFavorite(), write()

### Community 22 - "_handle_comment_post"
Cohesion: 0.33
Nodes (6): blog_comment(), _handle_comment_post(), _hmac_hex(), recipe_comment(), recipe_rate(), _voter_hash_from_cookie()

### Community 23 - "_save_blog_form"
Cohesion: 0.53
Nodes (6): blog_create(), blog_edit(), redaktor_blog_create(), redaktor_blog_edit(), _render_blog_form(), _save_blog_form()

### Community 24 - "_fold"
Cohesion: 0.40
Nodes (4): _fold(), _ingredient_matches(), match_recipe_ingredients(), is_basic()

### Community 25 - "shopping.js"
Cohesion: 0.60
Nodes (5): aggregate(), amountText(), formatNumber(), parseAmount(), render()

### Community 26 - "sw.js"
Cohesion: 0.47
Nodes (4): handleImage(), handlePage(), PRECACHE, trimCache()

### Community 27 - "_build_backup_zip"
Cohesion: 0.40
Nodes (4): backup_export(), _build_backup_zip(), export_backup(), _export_reader_data()

### Community 28 - "_sanitize_and_save_image"
Cohesion: 0.50
Nodes (4): blog_upload_images(), _extract_backup_images(), _sanitize_and_save_image(), _save_uploaded_image()

## Knowledge Gaps
- **11 isolated node(s):** `Cooking / Recipe Preparation Theme`, `Red-Tinted Hand-Drawn Line-Art Style, Circular Crop`, `Environment variables (.env, APP_ENV, SECRET_KEY...)`, `Flask`, `Flask-Login` (+6 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 156 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **9 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `create_app()` connect `create_app` to `admin_stats`, `Recipe create/edit form`, `sitemap_xml`, `Users & Editor Accounts`, `App Imports`, `Recipe Model Logic`, `Backup export/import page`, `Configuration`, `models.py`, `SQLite Pragmas`, `WSGI Entry`, `recipe_detail`, `Base layout template`, `_handle_comment_post`, `_save_blog_form`, `_build_backup_zip`, `_sanitize_and_save_image`?**
  _High betweenness centrality (0.367) - this node is a cross-community bridge._
- **Are the 9 inferred relationships involving `Recipe` (e.g. with `serialize_ingredient_entries()` and `Recipe approval queue (/admin/kolejka)`) actually correct?**
  _`Recipe` has 9 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Cooking / Recipe Preparation Theme`, `Red-Tinted Hand-Drawn Line-Art Style, Circular Crop`, `Environment variables (.env, APP_ENV, SECRET_KEY...)` to the rest of the system?**
  _11 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `create_app` be split into smaller, more focused modules?**
  _Cohesion score 0.07142857142857142 - nodes in this community are weakly interconnected._
- **Why does `Recipe` connect `Recipe Model Logic` to `create_app`, `Recipe create/edit form`, `README Docs & Security`, `App Imports`, `Recipe Scaling & Nutrition`, `models.py`, `Base layout template`?**
  _High betweenness centrality (0.164) - this node is a cross-community bridge._
- **Are the 3 inferred relationships involving `User` (e.g. with `Redaktor (editor) role` and `Admin dashboard template`) actually correct?**
  _`User` has 3 INFERRED edges - model-reasoned connections that need verification._
- **Should `Recipe create/edit form` be split into smaller, more focused modules?**
  _Cohesion score 0.08522727272727272 - nodes in this community are weakly interconnected._