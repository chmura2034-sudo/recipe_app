# Graph Report - recipe_app  (2026-11-02)

## Corpus Check
- 11 files · ~19,889 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 12 file(s) not represented in the graph (top: .example 5, (none) 4, .ini 1)

## Summary
- 322 nodes · 557 edges · 21 communities (12 shown, 9 thin omitted)
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 57 edges (avg confidence: 0.9)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `572ddfa0`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- App Factory & Backup
- Recipe create/edit form
- README Docs & Security
- Users & Editor Accounts
- Recipe Model Logic
- Alembic Migrations
- Tag
- Recipe Scaling & Nutrition
- Configuration
- BlogPost
- Access Decorators
- models.py
- Logo Branding
- SQLite Pragmas
- blog_editor.js
- Comment
- RecipeRating
- _escape_like

## God Nodes (most connected - your core abstractions)
1. `create_app()` - 91 edges
2. `Recipe` - 29 edges
3. `Wielka Księga Przepisów README` - 25 edges
4. `User` - 20 edges
5. `Recipe create/edit form` - 15 edges
6. `Base layout template` - 14 edges
7. `Recipe detail page` - 14 edges
8. `Tag` - 12 edges
9. `BlogPost` - 12 edges
10. `Admin dashboard template` - 12 edges

## Surprising Connections (you probably didn't know these)
- `ingredients_structured JSON serializer (submit handler)` --shares_data_with--> `serialize_ingredient_entries()`  [INFERRED]
  templates/admin/recipe_form.html → app.py
- `index()` --references--> `Public recipe list page`  [INFERRED]
  app.py → templates/index.html
- `recipe_detail()` --references--> `Recipe detail page`  [INFERRED]
  app.py → templates/recipe_detail.html
- `Image dropzone with clipboard paste` --shares_data_with--> `_sanitize_and_save_image()`  [INFERRED]
  templates/admin/recipe_form.html → app.py
- `Admin dashboard template` --references--> `User`  [INFERRED]
  templates/admin/dashboard.html → models.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Built-in security measures** — readme_sql_injection_protection, readme_xss_csp_protection, readme_safe_redirect, readme_timing_attack_protection, readme_logout_post_only, readme_proxy_count, readme_zip_bomb_protection, readme_strong_passwords, readme_image_sanitization, readme_login_rate_limiting, readme_csrf_protection [EXTRACTED 1.00]
- **Client-side recipe scaling (servings/pan area) incl. nutrition** — templates_recipe_detail_scale_panel, templates_recipe_detail_applyscale, templates_recipe_detail_areafor, templates_recipe_detail_updatenutrition, templates_recipe_detail_resetscale, templates_recipe_detail_nutrition_summary [EXTRACTED 1.00]
- **Recipe approval workflow (editor submits, admin approves/rejects)** — templates_redaktor_dashboard, templates_admin_recipe_form, templates_admin_queue, templates_admin_queue_reject_form, readme_approval_queue, app_create_app_recipe_approve, app_create_app_recipe_reject [INFERRED 0.85]

## Communities (21 total, 9 thin omitted)

### Community 0 - "App Factory & Backup"
Cohesion: 0.06
Nodes (31): create_app(), backup_export(), blog_comment(), blog_create(), blog_detail(), blog_edit(), blog_upload_images(), _build_backup_zip() (+23 more)

### Community 1 - "Recipe create/edit form"
Cohesion: 0.09
Nodes (27): admin_dashboard(), _build_instructions_text(), logout(), recipe_approve(), recipe_create(), recipe_delete(), recipe_edit(), redaktor_dashboard() (+19 more)

### Community 2 - "README Docs & Security"
Cohesion: 0.07
Nodes (22): change_own_password(), comment_delete(), login(), _post_login_redirect_endpoint(), is_safe_redirect_target(), Wielka Księga Przepisów README, Environment variables (.env, APP_ENV, SECRET_KEY...), Production deployment (Docker or gunicorn+nginx+systemd) (+14 more)

### Community 3 - "Users & Editor Accounts"
Cohesion: 0.10
Nodes (10): editor_create(), editor_delete(), editor_reset_password(), editors_page(), recipe_reject(), validate_new_password(), User, Editor accounts management page (+2 more)

### Community 6 - "Alembic Migrations"
Cohesion: 0.12
Nodes (8): get_engine(), get_engine_url(), get_metadata(), run_migrations_offline(), run_migrations_online(), upgrade(), upgrade(), upgrade()

### Community 7 - "Tag"
Cohesion: 0.11
Nodes (16): _clean_line_field(), backup_import(), backup_page(), _build_ingredients_text(), _extract_backup_images(), _restore_recipe_from_backup(), _save_tags(), serialize_ingredient_entries() (+8 more)

### Community 8 - "Recipe Scaling & Nutrition"
Cohesion: 0.21
Nodes (10): updatePanFields(), applyScale(), areaFor(), formatNumber(), Nutrition summary (total / per serving), panDimensionsText(), resetScale(), Recipe scale panel (servings / pan) (+2 more)

### Community 9 - "Configuration"
Cohesion: 0.16
Nodes (5): Config, DevelopmentConfig, get_config(), TestingConfig, validate_production_config()

### Community 11 - "Access Decorators"
Cohesion: 0.33
Nodes (3): admin_required(), wrapped(), redaktor_or_admin_required()

### Community 12 - "models.py"
Cohesion: 0.22
Nodes (4): blog_preview(), _blog_attribute_filter(), blog_markdown_to_plain_text(), render_blog_markdown()

### Community 13 - "Logo Branding"
Cohesion: 0.50
Nodes (5): Young Chef in White Double-Breasted Jacket, Cooking / Recipe Preparation Theme, Red-Tinted Hand-Drawn Line-Art Style, Circular Crop, Recipe App Logo (Chef Illustration), Large Steel Mixing Bowl with Red Sauce Being Whisked

### Community 15 - "blog_editor.js"
Cohesion: 0.42
Nodes (7): insertBlock(), prefixLines(), replaceSelection(), selectedText(), setStatus(), uploadImages(), wrap()

## Knowledge Gaps
- **11 isolated node(s):** `Flash messages block`, `Recipe title search form`, `Tag filter chips`, `Cooking / Recipe Preparation Theme`, `Red-Tinted Hand-Drawn Line-Art Style, Circular Crop` (+6 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 129 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **9 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `create_app()` connect `App Factory & Backup` to `Recipe create/edit form`, `README Docs & Security`, `Users & Editor Accounts`, `App Imports`, `Recipe Model Logic`, `Tag`, `Configuration`, `BlogPost`, `models.py`, `SQLite Pragmas`, `WSGI Entry`, `Comment`, `RecipeRating`?**
  _High betweenness centrality (0.395) - this node is a cross-community bridge._
- **Are the 9 inferred relationships involving `Recipe` (e.g. with `serialize_ingredient_entries()` and `Recipe approval queue (/admin/kolejka)`) actually correct?**
  _`Recipe` has 9 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Flash messages block`, `Recipe title search form`, `Tag filter chips` to the rest of the system?**
  _11 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `App Factory & Backup` be split into smaller, more focused modules?**
  _Cohesion score 0.06274509803921569 - nodes in this community are weakly interconnected._
- **Why does `Recipe` connect `Recipe Model Logic` to `App Factory & Backup`, `Recipe create/edit form`, `README Docs & Security`, `App Imports`, `Tag`, `models.py`?**
  _High betweenness centrality (0.199) - this node is a cross-community bridge._
- **Are the 3 inferred relationships involving `User` (e.g. with `Redaktor (editor) role` and `Admin dashboard template`) actually correct?**
  _`User` has 3 INFERRED edges - model-reasoned connections that need verification._
- **Should `Recipe create/edit form` be split into smaller, more focused modules?**
  _Cohesion score 0.0944741532976827 - nodes in this community are weakly interconnected._