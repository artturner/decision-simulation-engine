# API Reference (MVP)

Base: /v1

## Public
GET /public/scenarios/{slug}
POST /public/plays/start
GET /public/plays/{play_id}
POST /public/plays/{play_id}/step
POST /public/plays/{play_id}/back
POST /public/plays/{play_id}/reflection

## Admin (X-Admin-Key)
POST /admin/scenarios/import
POST /admin/scenarios/{scenario_id}/versions
POST /admin/scenarios/{scenario_id}/versions/{version_number}/publish
GET /admin/scenarios/{scenario_id}/analytics
GET /admin/scenarios/{scenario_id}/export.csv
