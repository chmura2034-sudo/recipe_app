# Graph Report - recipe_app  (2026-11-02)

## Corpus Check
- 10 files · ~17,538 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 14 file(s) not represented in the graph (top: .example 5, (none) 3, .ini 1)

## Summary
- 294 nodes · 508 edges · 18 communities (12 shown, 6 thin omitted)
- Extraction: 89% EXTRACTED · 11% INFERRED · 0% AMBIGUOUS · INFERRED: 57 edges (avg confidence: 0.9)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `9799c0d4`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- App Factory & Backup
- Base layout template
- README Docs & Security
- Users & Editor Accounts
- Recipe Model Logic
- Alembic Migrations
- Recipe create/edit form
- Recipe Scaling & Nutrition
- Configuration
- BlogPost
- Access Decorators
- models.py
- Logo Branding
- SQLite Pragmas
- blog_editor.js

## God Nodes (most connected - your core abstractions)
1. `create_app()` - 77 edges
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
- `login()` --references--> `Error page template`  [INFERRED]
  app.py → templates/errors.html
- `login()` --references--> `Login page template`  [INFERRED]
  app.py → templates/login.html
- `admin_dashboard()` --references--> `Admin dashboard template`  [INFERRED]
  app.py → templates/admin/dashboard.html
- `recipe_edit()` --references--> `Recipe create/edit form`  [INFERRED]
  app.py → templates/admin/recipe_form.html
- `redaktor_dashboard()` --references--> `Redaktor (editor) dashboard`  [INFERRED]
  app.py → templates/redaktor/dashboard.html

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Built-in security measures** — readme_sql_injection_protection, readme_xss_csp_protection, readme_safe_redirect, readme_timing_attack_protection, readme_logout_post_only, readme_proxy_count, readme_zip_bomb_protection, readme_strong_passwords, readme_image_sanitization, readme_login_rate_limiting, readme_csrf_protection [EXTRACTED 1.00]
- **Client-side recipe scaling (servings/pan area) incl. nutrition** — templates_recipe_detail_scale_panel, templates_recipe_detail_applyscale, templates_recipe_detail_areafor, templates_recipe_detail_updatenutrition, templates_recipe_detail_resetscale, templates_recipe_detail_nutrition_summary [EXTRACTED 1.00]
- **Recipe approval workflow (editor submits, admin approves/rejects)** — templates_redaktor_dashboard, templates_admin_recipe_form, templates_admin_queue, templates_admin_queue_reject_form, readme_approval_queue, app_create_app_recipe_approve, app_create_app_recipe_reject [INFERRED 0.85]

## Communities (18 total, 6 thin omitted)

### Community 0 - "App Factory & Backup"
Cohesion: 0.06
Nodes (32): create_app(), admin_dashboard(), backup_export(), backup_import(), backup_page(), blog_create(), blog_edit(), blog_upload_images() (+24 more)

### Community 1 - "Base layout template"
Cohesion: 0.11
Nodes (23): index(), recipe_approve(), recipe_delete(), recipe_detail(), recipe_edit(), recipe_reject(), redaktor_recipe_delete(), redaktor_recipe_edit() (+15 more)

### Community 2 - "README Docs & Security"
Cohesion: 0.09
Nodes (16): is_safe_redirect_target(), Wielka Księga Przepisów README, Environment variables (.env, APP_ENV, SECRET_KEY...), Production deployment (Docker or gunicorn+nginx+systemd), requirements.txt dependencies, Flask, Flask-Limiter, Flask-Login (+8 more)

### Community 3 - "Users & Editor Accounts"
Cohesion: 0.11
Nodes (8): editor_create(), editor_delete(), editor_reset_password(), editors_page(), validate_new_password(), User, Editor accounts management page, Editor password reset toggle form

### Community 6 - "Alembic Migrations"
Cohesion: 0.14
Nodes (7): get_engine(), get_engine_url(), get_metadata(), run_migrations_offline(), run_migrations_online(), upgrade(), upgrade()

### Community 7 - "Recipe create/edit form"
Cohesion: 0.11
Nodes (17): _clean_line_field(), _build_ingredients_text(), _build_instructions_text(), recipe_create(), redaktor_recipe_create(), _restore_recipe_from_backup(), _save_recipe_form(), _save_tags() (+9 more)

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
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 117 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **6 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `create_app()` connect `App Factory & Backup` to `Base layout template`, `Users & Editor Accounts`, `App Imports`, `Recipe Model Logic`, `Recipe create/edit form`, `Configuration`, `BlogPost`, `models.py`, `SQLite Pragmas`, `WSGI Entry`?**
  _High betweenness centrality (0.364) - this node is a cross-community bridge._
- **Are the 9 inferred relationships involving `Recipe` (e.g. with `serialize_ingredient_entries()` and `Recipe approval queue (/admin/kolejka)`) actually correct?**
  _`Recipe` has 9 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Flash messages block`, `Recipe title search form`, `Tag filter chips` to the rest of the system?**
  _11 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `App Factory & Backup` be split into smaller, more focused modules?**
  _Cohesion score 0.06184012066365008 - nodes in this community are weakly interconnected._
- **Why does `Recipe` connect `Recipe Model Logic` to `App Factory & Backup`, `Base layout template`, `README Docs & Security`, `App Imports`, `Recipe create/edit form`, `models.py`?**
  _High betweenness centrality (0.216) - this node is a cross-community bridge._
- **Are the 3 inferred relationships involving `User` (e.g. with `Redaktor (editor) role` and `Admin dashboard template`) actually correct?**
  _`User` has 3 INFERRED edges - model-reasoned connections that need verification._
- **Should `Base layout template` be split into smaller, more focused modules?**
  _Cohesion score 0.10574712643678161 - nodes in this community are weakly interconnected._