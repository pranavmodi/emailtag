def test_research_tasks_route_to_research_queue_and_live_pipeline_stays_processing():
    from app.tasks.worker import celery_app

    routes = celery_app.conf.task_routes
    research_tasks = [
        "app.tasks.firm_research.research_firm_task",
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

    assert routes["app.tasks.pif_extraction.extract_pif_from_conversation"]["queue"] == "processing"
    assert routes["app.tasks.email.perform_autorespond_task"]["queue"] == "processing"
    assert routes.get("app.tasks.autorespond.perform_autorespond_task", {}).get("queue") != "research"


def test_research_tasks_have_rate_limits():
    import app.tasks.behavior_analysis as behavior_analysis
    import app.tasks.firm_research as firm_research
    import app.tasks.signature_extraction as signature_extraction

    assert firm_research.research_firm_task.rate_limit == "10/m"
    assert firm_research.research_staff_task.rate_limit == "10/m"
    assert firm_research.analyze_leadership_emails_task.rate_limit == "10/m"
    import app.tasks.website_resolution as website_resolution

    assert website_resolution.resolve_firm_website_task.rate_limit == "10/m"
    assert behavior_analysis.analyze_firm_behavior_task.rate_limit == "10/m"
    assert behavior_analysis.analyze_all_firms_task.rate_limit == "10/m"
    assert behavior_analysis.score_all_firms_task.rate_limit == "10/m"
    assert signature_extraction.extract_signatures_task.rate_limit == "10/m"
