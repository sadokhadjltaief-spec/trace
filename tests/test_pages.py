"""Smoke-run the stub pages with Streamlit's AppTest (no browser)."""
import pytest
from streamlit.testing.v1 import AppTest

from engine import ROOT, api_fake

PAGES = ["pages/1_Learn.py", "pages/2_Judge_Panel.py", "pages/3_Results.py", "pages/4_Report.py",
         "pages/5_Study_Studio.py"]


def test_onboarding_creates_session():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)
    at.session_state["data_source"] = "fake fixtures"
    at.run()
    assert not at.exception
    at.text_input[0].input("Sami")
    at.button[0].click().run()
    assert not at.exception
    assert at.session_state["session"]["student"]["name"] == "Sami"


@pytest.mark.parametrize("page", PAGES)
def test_page_runs_with_fake_data(page):
    at = AppTest.from_file(str(ROOT / page), default_timeout=30)
    at.session_state["data_source"] = "fake fixtures"
    at.session_state["session"] = api_fake.start_session({"name": "Sami"})
    at.run()
    assert not at.exception, at.exception


def test_studio_shows_targeted_at_line():
    at = AppTest.from_file(str(ROOT / "pages/5_Study_Studio.py"), default_timeout=30)
    at.session_state["data_source"] = "fake fixtures"
    at.session_state["session"] = api_fake.start_session({"name": "Sami"})
    at.run()
    at.button[0].click().run()
    assert any("Targeted at:" in m.value for m in at.markdown)
