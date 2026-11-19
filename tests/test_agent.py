import io
import json
import os
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from src.agent import add_sources, check_finding, run
from src.providers import ProviderError, Providers


PASSAGE = "Local transcription must be explicitly enabled in this release."
REQ = {"id": "R1", "requirement": "Local transcription is enabled by default."}
PAGE = {"title": "Example release", "url": "https://example.org/releases/1", "raw_content": PASSAGE}
SOURCES = {"S1": {"passages": [PASSAGE]}}


def finding(status="contradicted", stance="contradicts", quote=PASSAGE, source_id="S1"):
    return {"id": "R1", "status": status, "answer": "The default configuration permits remote processing.",
            "evidence": [{"source_id": source_id, "stance": stance, "quote": quote}]}


class Scripted:
    model = "offline-test-double"

    def __init__(self, searches, assessments, requirements=None):
        self.searches = iter(searches)
        plan = {"requirements": requirements or [REQ["requirement"]], "queries": ["local processing default release"]}
        self.answers = iter([plan, *assessments])
        self.queries = []

    def ask(self, instruction, data):
        return next(self.answers)

    def search(self, query):
        self.queries.append(query)
        response = next(self.searches)
        if isinstance(response, Exception):
            raise response
        return response


class EvidenceTests(unittest.TestCase):
    def test_rejects_wrong_source_and_invented_quote(self):
        for item in (finding(source_id="S22"), finding(quote="This feature always runs offline.")):
            with self.subTest(item=item):
                checked = check_finding(REQ, item, SOURCES)
                self.assertEqual((checked["status"], checked["evidence"]), ("unverified", []))

    def test_preserves_requirements_and_attaches_an_exact_quote(self):
        providers = Scripted([[PAGE]], [{"findings": [finding()]}], [REQ["requirement"], "Malay works on the installed device."])
        report = run("Does it work locally by default, including in Malay?", providers)
        self.assertEqual([f["status"] for f in report["findings"]], ["contradicted", "unverified"])
        self.assertEqual(report["findings"][0]["evidence"][0]["quote"], PASSAGE)
        self.assertEqual(report["sources"][0]["url"], PAGE["url"])
        self.assertEqual([e["action"] for e in report["trace"]], ["plan", "search", "assess"])

    def test_one_real_quote_cannot_validate_a_finding_with_a_second_invented_quote(self):
        row = finding()
        row["evidence"].append({"source_id": "S1", "stance": "contradicts", "quote": "Fabricated qualification."})
        checked = check_finding(REQ, row, SOURCES)
        self.assertEqual((checked["status"], checked["evidence"]), ("unverified", []))

    def test_handles_empty_results_and_provider_failure_separately(self):
        for response, failed in (([], False), (ProviderError("Tavily returned HTTP 429."), True)):
            with self.subTest(response=response):
                report = run("Is the feature local?", Scripted([response], []))
                self.assertEqual(report["findings"][0]["status"], "unverified")
                self.assertEqual("error" in report["trace"][-1], failed)

    def test_cannot_use_a_search_snippet_as_a_page_quote(self):
        report = run("Is the feature local?", Scripted([[{**PAGE, "raw_content": None, "content": PASSAGE}]], []))
        self.assertEqual(report["sources"], [])
        self.assertEqual(report["findings"][0]["evidence"], [])

    def test_tracking_duplicates_share_one_id_and_keep_original_link(self):
        sources = []
        link = PAGE["url"] + "?utm_source=release"
        add_sources(sources, [{**PAGE, "url": link}, PAGE], "transcription")
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]["url"], link)
        self.assertEqual(sources[0]["passages"], [PASSAGE])

    def test_conflict_needs_two_opposed_sources(self):
        row = finding(status="conflicting")
        row["evidence"].append({"stance": "supports", "source_id": "S1", "quote": PASSAGE})
        self.assertEqual(check_finding(REQ, row, SOURCES)["status"], "unverified")
        other = "This edition processes speech locally by default."
        row["evidence"][1].update(source_id="S2", quote=other)
        self.assertEqual(check_finding(REQ, row, {**SOURCES, "S2": {"passages": [other]}})["status"], "conflicting")

    def test_follow_up_only_once_even_when_model_requests_more(self):
        second = {**PAGE, "url": "https://example.org/edition-2"}
        more = {"findings": [], "follow_up_query": "exact installation requirements"}
        providers = Scripted([[PAGE], [second]], [more, {**more, "follow_up_query": "yet another search"}])
        report = run("Is the feature local?", providers)
        self.assertEqual(len(providers.queries), 2)
        self.assertEqual(len(report["sources"]), 2)
        self.assertEqual(report["findings"][0]["status"], "unverified")

    def test_repeated_search_without_new_passages_keeps_original_assessment(self):
        row = finding(status="conditional", stance="qualifies")
        providers = Scripted([[PAGE], [PAGE]], [{"findings": [row], "follow_up_query": "model release conditions"}])
        report = run("Is the feature local?", providers)
        self.assertEqual(len(providers.queries), 2)
        self.assertEqual([f["status"] for f in report["findings"]], ["conditional"])
        self.assertEqual(sum(e["action"] == "assess" for e in report["trace"]), 1)

    def test_malformed_evidence_or_status_downgrades_to_unverified(self):
        row = {**finding(), "evidence": 4}
        self.assertEqual(check_finding(REQ, row, SOURCES)["status"], "unverified")
        row = {**finding(), "status": ["contradicted"]}
        self.assertEqual(check_finding(REQ, row, SOURCES)["status"], "unverified")


class ProviderTests(unittest.TestCase):
    @patch.dict(os.environ, {}, clear=True)
    def test_lists_missing_key_names_without_network(self):
        with self.assertRaisesRegex(ProviderError, "NEBIUS_API_KEY.*TAVILY_API_KEY"):
            Providers()

    @patch.dict(os.environ, {"NEBIUS_API_KEY": "offline-model-key", "TAVILY_API_KEY": "offline-search-key"}, clear=True)
    @patch("src.providers.urlopen")
    def test_exercises_both_http_contracts_and_excludes_model_reasoning(self, transport):
        reply = {"choices": [{"message": {"content": '{"findings":[]}', "reasoning_content": "not for the report"}}]}
        transport.side_effect = [io.BytesIO(json.dumps(reply).encode()), io.BytesIO(b'{"results":[]}')]
        clients = Providers()
        self.assertEqual(clients.ask("Return JSON", {"question": "Example?"}), {"findings": []})
        self.assertEqual(clients.search("query"), [])
        model_req, search_req = [call.args[0] for call in transport.call_args_list]
        self.assertEqual(model_req.full_url, "https://api.tokenfactory.nebius.com/v1/chat/completions")
        self.assertEqual(search_req.full_url, "https://api.tavily.com/search")
        self.assertEqual(json.loads(search_req.data)["include_raw_content"], "markdown")
        self.assertNotEqual(model_req.get_header("Authorization"), search_req.get_header("Authorization"))

    @patch.dict(os.environ, {"NEBIUS_API_KEY": "offline-model-key", "TAVILY_API_KEY": "offline-search-key"}, clear=True)
    @patch("src.providers.urlopen", side_effect=HTTPError("https://api.tavily.com/search", 401, "bad token detail", {}, None))
    def test_http_error_omits_credentials_and_response_body(self, _):
        with self.assertRaises(ProviderError) as caught:
            Providers().search("test")
        self.assertIn("HTTP 401", str(caught.exception))
        self.assertNotIn("offline-search-key", str(caught.exception))
        self.assertNotIn("bad token detail", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
