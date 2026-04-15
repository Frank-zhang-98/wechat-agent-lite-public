from __future__ import annotations

from app.runtime.audit import record_node_audit


def build_render_article_node(support):
    def _node(state: dict) -> dict:
        draft = state["article_draft"]
        title_plan = state["title_plan_state"]
        visual_assets = state["visual_assets_state"]
        intent = state["article_intent"]
        diagnostics = dict(state.get("visual_diagnostics") or {})
        rendered = support.article_renderer.render(
            draft.article_markdown,
            article_title=title_plan.article_title,
            pool=intent.pool,
            subtype=intent.subtype,
            target_audience=intent.audience,
            illustrations=list(visual_assets.body_assets or []),
            run_id=state["run"].id,
        )
        html_path = support.article_renderer.save_html(rendered, state["run"].id)
        article_layout = {
            "name": rendered.layout_name,
            "label": rendered.layout_label,
            "description": rendered.description,
            "source": rendered.source,
            "pool": intent.pool,
            "subtype": intent.subtype,
        }
        qualified_body_asset_count = int(diagnostics.get("qualified_body_asset_count", len(list(visual_assets.body_assets or []))) or 0)
        render_anchor_failures = list(rendered.render_anchor_failures or [])
        visual_fit_failures = list(diagnostics.get("visual_fit_failures") or [])
        if rendered.inserted_illustration_count > 0:
            visual_body_result = "inserted"
        elif bool(diagnostics.get("omitted_by_policy")):
            visual_body_result = "omitted_by_decision"
        elif qualified_body_asset_count > 0 and render_anchor_failures:
            visual_body_result = "anchor_failed"
        else:
            visual_body_result = "no_qualified_assets"
        visual_body_warning = (
            visual_body_result != "inserted"
            or bool(visual_fit_failures)
            or bool(render_anchor_failures)
        )
        article_render = {
            "html_path": html_path,
            "html_length": len(rendered.html),
            "block_count": rendered.block_count,
            "inserted_illustration_count": rendered.inserted_illustration_count,
            "qualified_body_asset_count": qualified_body_asset_count,
            "visual_fit_failures": visual_fit_failures,
            "render_anchor_failures": render_anchor_failures,
            "visual_body_result": visual_body_result,
            "visual_body_warning": visual_body_warning,
        }
        output = dict(state)
        output.update(
            {
                "article_layout": article_layout,
                "article_render": article_render,
                "article_html": rendered.html,
                "node_audits": record_node_audit(
                    state,
                    "RENDER_ARTICLE",
                    {"outputs": [{"title": "runtime_article_render", "text": str(article_render), "language": "json"}]},
                ),
            }
        )
        return output

    return _node
