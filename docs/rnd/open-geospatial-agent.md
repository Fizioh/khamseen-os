# R&D — Open Geospatial Agent

> Status: research plan. No ArcGIS copilot shipped by this document.

**Future standalone repository:** `khamseen-geospatial-agent` (not created yet). This project is distinct from the existing [Fizioh/GeoAgent](https://github.com/Fizioh/GeoAgent) fork; do not overwrite the upstream-derived code.

## Problem
Answer bounded natural-language geospatial questions against permitted datasets, show results on an interactive map, and supply reproducible evidence for each computation.

## V0 demo
"Find schools within 500 m of flood-risk zones; show results on the map, and count by municipality." All data must be licensed/open demo data.

## Proposed architecture
- React / TypeScript UI; ArcGIS Experience Builder custom widget as optional frontend adapter.
- Python / Django DRF tool gateway with allowlisted actions and read-only database permissions.
- PostGIS for deterministic distance/intersection/count operations (SRID selection documented).
- GeoJSON provenance: dataset version, query plan, applied filters, CRS, units, result checksum.
- Optional MCP tool surface; never grant the LLM arbitrary SQL or tool escalation.

## Acceptance criteria
- Deterministic fixture tests for CRS, distances, invalid geometry and empty results.
- Query is read-only, schema-scoped, bounded by time/rows/cost and logged.
- Natural-language narrative can be cross-checked against computed structured output.
- No invented geospatial features/counts; unknown fields explicitly marked.
- A runnable public demo with no sensitive imagery or client data.

## Links
- [R&D Notion hub](https://app.notion.com/p/3fc524057c2f81a081e4f3f2739f32ea)
- [R&D Linear project](https://linear.app/khamseen/project/khamseen-randd-frontier-tech-lab-2027-b15f6fbc3e25)
- [Existing Agentic GIS strategy](https://app.notion.com/p/3fa524057c2f816fb8d9e3073883e233)
