import unittest

from app.services.article_variant_policy import classify_article_variant, extract_project_subject, extract_repo_url


class ArticleVariantPolicyTests(unittest.TestCase):
    def test_classify_project_explainer_for_repo_system_article(self) -> None:
        result = classify_article_variant(
            topic={
                "title": "RAG isn't enough: I built the missing context layer that makes LLM systems work",
                "summary": "A deep dive into a GitHub project and its context-engine architecture.",
            },
            fact_pack={
                "primary_pool": "deep_dive",
                "section_blueprint": [
                    {"heading": "System architecture", "summary": "How the context layer is composed of modules."},
                    {"heading": "Benchmark and evaluation", "summary": "Latency and retrieval quality compared against baselines."},
                ],
                "implementation_steps": [{"title": "Pipeline", "summary": "How requests move through the system."}],
                "architecture_points": [{"component": "Context Engine", "responsibility": "Routes and composes context."}],
                "code_artifacts": [{"section": "context_engine.py", "summary": "Core routing implementation"}],
                "github_repo_url": "https://github.com/example/context-engine",
            },
        )

        self.assertEqual(result["article_variant"], "project_explainer")
        self.assertIn("project_signal", result["matched_features"])
        self.assertIn("implementation_signal", result["matched_features"])

    def test_classify_project_explainer_does_not_misclassify_financing_style_article(self) -> None:
        result = classify_article_variant(
            topic={
                "title": "Startup raises funding to expand its AI platform",
                "summary": "Investors back the company despite platform and API ambitions.",
            },
            fact_pack={
                "primary_pool": "deep_dive",
                "section_blueprint": [{"heading": "Funding", "summary": "Investment and valuation update."}],
                "implementation_steps": [],
                "architecture_points": [],
                "code_artifacts": [],
            },
        )

        self.assertEqual(result["article_variant"], "standard")
        self.assertTrue(result["blocked_by"])

    def test_extract_repo_url_and_project_subject_from_grounded_fact_text(self) -> None:
        fact_pack = {
            "grounded_hard_facts": [
                "文章提供了完整的代码实现链接：https://github.com/Emmimal/context-engine/。"
            ],
            "source_lead": "A repo-backed context engine walkthrough.",
        }

        repo_url = extract_repo_url(
            topic={"title": "RAG isn't enough", "summary": "A context-engine article."},
            fact_pack=fact_pack,
        )
        subject = extract_project_subject(
            topic={"title": "RAG isn't enough", "summary": "A context-engine article."},
            fact_pack={**fact_pack, "github_repo_url": repo_url},
        )

        self.assertEqual(repo_url, "https://github.com/Emmimal/context-engine")
        self.assertEqual(subject, "context-engine")


if __name__ == "__main__":
    unittest.main()
