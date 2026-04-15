import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import LLMCall, Run, RunStatus
from app.services import metrics_service
from app.services.metrics_service import _token_bucket, get_token_overview


class MetricsServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", future=True)
        Base.metadata.create_all(self.engine)
        SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, future=True)
        self.session = SessionLocal()
        metrics_service._TOKEN_OVERVIEW_CACHE.update({"generated_at": 0.0, "latest_call_id": 0, "latest_run_id": "", "value": None})

    def tearDown(self) -> None:
        self.session.close()
        self.engine.dispose()
        metrics_service._TOKEN_OVERVIEW_CACHE.update({"generated_at": 0.0, "latest_call_id": 0, "latest_run_id": "", "value": None})

    def test_token_bucket_excludes_mock_and_blank_model_records(self) -> None:
        run = Run(
            id="run-1",
            run_type="main",
            status=RunStatus.success.value,
            started_at=datetime.now(timezone.utc),
        )
        self.session.add(run)
        self.session.flush()
        self.session.add_all(
            [
                LLMCall(
                    run_id=run.id,
                    step_name="WRITE",
                    role="writer",
                    provider="alibaba-bailian",
                    model="qwen-plus",
                    prompt_tokens=120,
                    completion_tokens=30,
                    total_tokens=150,
                ),
                LLMCall(
                    run_id=run.id,
                    step_name="WRITE",
                    role="writer",
                    provider="alibaba-bailian",
                    model="mock-model",
                    prompt_tokens=80,
                    completion_tokens=20,
                    total_tokens=100,
                ),
                LLMCall(
                    run_id=run.id,
                    step_name="WRITE",
                    role="writer",
                    provider="alibaba-bailian",
                    model="",
                    prompt_tokens=50,
                    completion_tokens=10,
                    total_tokens=60,
                ),
            ]
        )
        self.session.commit()

        bucket = _token_bucket(self.session, label="test", run_id=run.id, run=run)

        self.assertEqual(bucket["calls_count"], 1)
        self.assertEqual(bucket["total_tokens"], 150)
        self.assertEqual(bucket["excluded_mock_calls_count"], 1)
        self.assertEqual(bucket["excluded_invalid_calls_count"], 1)
        self.assertEqual(bucket["excluded_non_real_calls_count"], 2)
        self.assertEqual(bucket["costs"]["supported_calls_count"], 1)
        self.assertEqual(bucket["costs"]["unsupported_calls_count"], 0)

    def test_current_run_tracks_latest_run_even_when_only_non_real_calls_exist(self) -> None:
        real_run = Run(
            id="run-real",
            run_type="main",
            status=RunStatus.success.value,
            started_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        invalid_run = Run(
            id="run-invalid",
            run_type="main",
            status=RunStatus.partial_success.value,
            started_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        self.session.add_all([real_run, invalid_run])
        self.session.flush()
        self.session.add_all(
            [
                LLMCall(
                    run_id=real_run.id,
                    step_name="WRITE",
                    role="writer",
                    provider="alibaba-bailian",
                    model="qwen-plus",
                    prompt_tokens=100,
                    completion_tokens=20,
                    total_tokens=120,
                ),
                LLMCall(
                    run_id=invalid_run.id,
                    step_name="WRITE",
                    role="writer",
                    provider="alibaba-bailian",
                    model="",
                    prompt_tokens=90,
                    completion_tokens=20,
                    total_tokens=110,
                ),
            ]
        )
        self.session.commit()

        overview = get_token_overview(self.session)

        self.assertEqual(overview["windows"]["current_run"]["run_id"], invalid_run.id)
        self.assertEqual(overview["windows"]["current_run"]["calls_count"], 0)
        self.assertTrue(overview["windows"]["current_run"]["has_invalid_calls"])

    def test_current_run_marks_mock_only_latest_run_as_degraded(self) -> None:
        real_run = Run(
            id="run-real",
            run_type="main",
            status=RunStatus.success.value,
            started_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        mock_run = Run(
            id="run-mock",
            run_type="main",
            status=RunStatus.partial_success.value,
            started_at=datetime.now(timezone.utc) - timedelta(minutes=30),
        )
        self.session.add_all([real_run, mock_run])
        self.session.flush()
        self.session.add_all(
            [
                LLMCall(
                    run_id=real_run.id,
                    step_name="WRITE",
                    role="writer",
                    provider="alibaba-bailian",
                    model="qwen-plus",
                    prompt_tokens=100,
                    completion_tokens=20,
                    total_tokens=120,
                ),
                LLMCall(
                    run_id=mock_run.id,
                    step_name="WRITE",
                    role="writer",
                    provider="alibaba-bailian",
                    model="mock-model",
                    prompt_tokens=90,
                    completion_tokens=20,
                    total_tokens=110,
                ),
            ]
        )
        self.session.commit()

        overview = get_token_overview(self.session)

        self.assertEqual(overview["windows"]["current_run"]["run_id"], mock_run.id)
        self.assertTrue(overview["windows"]["current_run"]["has_mock_calls"])
        self.assertTrue(overview["windows"]["current_run"]["degraded_mode"])

    def test_token_overview_uses_short_lived_cache_when_inputs_do_not_change(self) -> None:
        run = Run(
            id="run-cache",
            run_type="main",
            status=RunStatus.success.value,
            started_at=datetime.now(timezone.utc),
        )
        self.session.add(run)
        self.session.flush()
        self.session.add(
            LLMCall(
                run_id=run.id,
                step_name="WRITE",
                role="writer",
                provider="alibaba-bailian",
                model="qwen-plus",
                prompt_tokens=100,
                completion_tokens=20,
                total_tokens=120,
            )
        )
        self.session.commit()

        with patch("app.services.metrics_service._token_bucket", wraps=metrics_service._token_bucket) as bucket_mock:
            first = get_token_overview(self.session)
            first_call_count = bucket_mock.call_count
            second = get_token_overview(self.session)

        self.assertEqual(first["windows"]["current_run"]["run_id"], run.id)
        self.assertEqual(second["windows"]["current_run"]["run_id"], run.id)
        self.assertEqual(first_call_count, 4)
        self.assertEqual(bucket_mock.call_count, first_call_count)


if __name__ == "__main__":
    unittest.main()
