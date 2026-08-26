def test_research_tasks_route_to_research_queue_and_live_pipeline_stays_processing():
    from app.tasks.worker import celery_app

    routes = celery_app.conf.task_routes
    research_tasks = [
        "app.tasks.firm_research.research_firm_task",
        "app.tasks.firm_research.research_job_postings_task",
        "app.tasks.firm_research.research_staff_task",
        "app.tasks.firm_research.analyze_leadership_emails_task",
        "app.tasks.website_resolution.resolve_firm_website_task",
        "app.tasks.behavior_analysis.analyze_firm_behavior_task",
        "app.tasks.behavior_analysis.analyze_all_firms_task",
        "app.tasks.behavior_analysis.score_all_firms_task",
        "app.tasks.signature_extraction.extract_signatures_task",
    ]

    for task_name in research_tasks:
        assert routes[task_name]["queue"] == "research"
        assert task_name in celery_app.tasks

    assert routes["app.tasks.pif_extraction.extract_pif_from_conversation"]["queue"] == "processing"
    assert routes["app.tasks.autorespond.perform_autorespond_task"]["queue"] == "processing"
    assert "app.tasks.autorespond.perform_autorespond_task" in celery_app.tasks


def test_research_tasks_have_rate_limits():
    import app.tasks.behavior_analysis as behavior_analysis
    import app.tasks.firm_research as firm_research
    import app.tasks.signature_extraction as signature_extraction

    assert firm_research.research_firm_task.rate_limit == "10/m"
    assert firm_research.research_job_postings_task.rate_limit == "10/m"
    assert firm_research.research_staff_task.rate_limit == "10/m"
    assert firm_research.analyze_leadership_emails_task.rate_limit == "10/m"
    import app.tasks.website_resolution as website_resolution

    assert website_resolution.resolve_firm_website_task.rate_limit == "10/m"
    assert behavior_analysis.analyze_firm_behavior_task.rate_limit == "10/m"
    assert behavior_analysis.analyze_all_firms_task.rate_limit == "10/m"
    assert behavior_analysis.score_all_firms_task.rate_limit == "10/m"
    assert signature_extraction.extract_signatures_task.rate_limit == "10/m"


def test_remaining_downstream_tasks_skip_before_opening_database(monkeypatch):
    import app.tasks.signature_extraction as signature_extraction
    import app.tasks.website_resolution as website_resolution

    monkeypatch.setattr(
        signature_extraction.settings,
        "PIF_DOWNSTREAM_ENRICHMENT_ENABLED",
        False,
    )
    monkeypatch.setattr(
        website_resolution.settings,
        "PIF_DOWNSTREAM_ENRICHMENT_ENABLED",
        False,
    )

    def fail_session():
        raise AssertionError("disabled task must not open a database session")

    monkeypatch.setattr(signature_extraction, "SessionLocal", fail_session)
    monkeypatch.setattr(website_resolution, "SessionLocal", fail_session)

    pif_id = str(uuid4())
    assert signature_extraction.extract_signatures_task.run(pif_id)["status"] == "skipped"
    assert website_resolution.resolve_firm_website_task.run(pif_id)["status"] == "skipped"


def test_disabled_research_task_clears_stale_running_status(monkeypatch):
    import app.tasks.firm_research as firm_research

    pif = SimpleNamespace(id=uuid4(), research_status="queued")

    class FakeQuery:
        def filter(self, *args):
            return self

        def first(self):
            return pif

    class FakeDb:
        committed = False

        def query(self, *args):
            return FakeQuery()

        def add(self, obj):
            pass

        def commit(self):
            self.committed = True

        def rollback(self):
            pass

        def close(self):
            pass

    fake_db = FakeDb()
    monkeypatch.setattr(firm_research.settings, "PIF_DOWNSTREAM_ENRICHMENT_ENABLED", False)
    monkeypatch.setattr(firm_research, "SessionLocal", lambda: fake_db)

    result = firm_research._disabled_result(
        str(pif.id),
        status_field="research_status",
    )

    assert result["status"] == "skipped"
    assert pif.research_status is None
    assert fake_db.committed is True
from types import SimpleNamespace
from uuid import uuid4
