"""weekly_digest.py: filtering, escaping, seen-state and source-health warnings."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import weekly_digest as wd  # noqa: E402


def job(title="DevOps Engineer", company="Acme", location="Bengaluru, India",
        url="https://example.com/j/1", portal="linkedin-search", date="2026-11-20"):
    return {"title": title, "company": company, "location": location,
            "url": url, "_portal": portal, "date": date}


class FilterTests(unittest.TestCase):
    def test_location_gate(self):
        for loc in ("Bengaluru, Karnataka, India", "Gurgaon/Gurugram", "Remote; India",
                    "Remote / Worldwide", "Remote", "", "None", ","):
            with self.subTest(loc=loc):
                self.assertTrue(wd.location_ok(loc))
        for loc in ("San Jose, CA", "United States (Remote)", "Москва", "Bern, Switzerland",
                    "Spain (Remote)"):
            with self.subTest(loc=loc):
                self.assertFalse(wd.location_ok(loc))

    def test_non_engineering_titles_dropped_but_ic_titles_kept(self):
        stats = {}
        out = wd.normalize_jobs([
            job("Engineering Manager, Core Infrastructure", url="https://e.com/1"),
            job("Technical Support Engineer (Inference)", url="https://e.com/2"),
            job("LLM Infra SRE Intern", url="https://e.com/3"),
            job("Deputy Manager - AWS DevOps & Performance Engineer", url="https://e.com/4"),
            job("Lead DevSecOps Engineer", url="https://e.com/5"),
        ], stats)
        self.assertEqual([j["url"] for j in out], ["https://e.com/4", "https://e.com/5"])
        self.assertEqual(stats["dropped"]["off-role"], 3)

    def test_non_http_urls_dropped(self):
        out = wd.normalize_jobs([job(url="javascript:alert(1)")])
        self.assertEqual(out, [])

    def test_sources_labelled(self):
        out = wd.normalize_jobs([job(portal="greenhouse"), job(portal="freehire-search", url="https://e.com/2")])
        self.assertEqual([j["portal"] for j in out], ["Company ATS", "freehire"])


class CategoryTests(unittest.TestCase):
    def test_spelling_variants_categorised(self):
        cases = {
            "Senior DevSecOps Engineer": "DevOps / Platform",
            "Jr. Dev Ops (Kubernetes) (24*7)": "DevOps / Platform",
            "Staff Engineer, Core Infrastructure": "DevOps / Platform",
            "(ML-Ops) Machine Learning Operations Engineer": "AI / LLM Infrastructure",
            "Performance Engineer, Inference": "AI / LLM Infrastructure",
            "Site Reliability Engineer - Platform": "SRE / Reliability",
        }
        for title, cat in cases.items():
            with self.subTest(title=title):
                self.assertTrue(wd.categorize(title).endswith(cat), wd.categorize(title))


class HtmlTests(unittest.TestCase):
    def test_fields_are_escaped(self):
        jobs = wd.normalize_jobs([job(title="DevOps <script>x</script> Engineer", company="A&B")])
        html = wd.build_html(jobs, "2026-11-26", {"warnings": ["LinkedIn returned 0 results"]})
        self.assertNotIn("<script>x", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("A&amp;B", html)
        self.assertIn("Source health warning", html)

    def test_empty_digest_says_so(self):
        self.assertIn("No new matching openings", wd.build_html([], "2026-11-26", {}))


class SeenStateTests(unittest.TestCase):
    def test_save_and_expire(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "state" / "seen.json"
            old = {"https://old.example/1": "2026-01-01", "https://recent.example/1": "2026-11-01"}
            wd.save_seen(path, old, wd.normalize_jobs([job()]), "2026-11-26")
            saved = json.loads(path.read_text())
            self.assertNotIn("https://old.example/1", saved)
            self.assertEqual(saved["https://recent.example/1"], "2026-11-01")
            self.assertEqual(saved["https://example.com/j/1"], "2026-11-26")
            self.assertEqual(wd.load_seen(path), saved)

    def test_missing_or_corrupt_state_is_empty(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(wd.load_seen(Path(d) / "nope.json"), {})
            bad = Path(d) / "bad.json"
            bad.write_text("{not json")
            self.assertEqual(wd.load_seen(bad), {})

    def test_newest_first_sort_key(self):
        dates = ["2026-11-01", "", "2026-11-20", "2026-10-05"]
        self.assertEqual(sorted(dates, key=wd._neg_date), ["2026-11-20", "2026-11-01", "2026-10-05", ""])


class CareerPageFilterTests(unittest.TestCase):
    def test_marketing_links_rejected(self):
        import scrape_companies as sc
        base = "https://cohere.com/careers"
        self.assertFalse(sc.looks_like_job("Aya Models Multilingual AI at scale", "https://cohere.com/research/aya", base))
        self.assertFalse(sc.looks_like_job("Platform Engineer jobs", "https://www.linkedin.com/jobs/platform-engineer-jobs", base))
        self.assertTrue(sc.looks_like_job("Platform Engineer - AI Infrastructure", "https://www.sarvam.ai/careers/jobs/abc", base))
        self.assertTrue(sc.looks_like_job("Senior SRE", "https://jobs.lever.co/acme/123", base))


if __name__ == "__main__":
    unittest.main()
