import unittest

from agent import (
    AgentResponse,
    format_count_answer,
    parse_catalogue_reporting_update,
    outcome_value,
    parse_catalogue_count_kind,
    solve_task,
    sql_tmpdir_args,
    submit_response,
)


class FakeClient:
    def __init__(self):
        self.requests = []
        self.exec_requests = []
        self.search_requests = []
        self.sql_stdout = "total\n7\n"
        self.sql_outputs = []
        self.identity_stdout = "uid=1000(employee)\n"
        self.checkout_exit_code = 0
        self.exec_failures = []
        self.search_paths = []
        self.read_contents = {}

    def answer(self, request):
        self.requests.append(request)

    def exec(self, request):
        self.exec_requests.append(request)
        if request.path == "/bin/id":
            return type("ExecResponse", (), {"stdout": self.identity_stdout, "stderr": "", "exit_code": 0})()
        if request.path == "/bin/checkout":
            basket_id = request.args[0] if request.args else ""
            return type(
                "ExecResponse",
                (),
                {
                    "stdout": f"checked out {basket_id}\n" if self.checkout_exit_code == 0 else "",
                    "stderr": "checkout unavailable\n" if self.checkout_exit_code else "",
                    "exit_code": self.checkout_exit_code,
                },
            )()
        if self.exec_failures:
            stderr = self.exec_failures.pop(0)
            return type(
                "ExecResponse",
                (),
                {"stdout": "", "stderr": stderr, "exit_code": 1},
            )()
        if self.sql_outputs:
            return type("ExecResponse", (), {"stdout": self.sql_outputs.pop(0), "stderr": "", "exit_code": 0})()
        return type("ExecResponse", (), {"stdout": self.sql_stdout, "stderr": "", "exit_code": 0})()

    def search(self, request):
        self.search_requests.append(request)
        paths = self.search_paths
        if isinstance(paths, dict):
            paths = paths.get(request.pattern, [])
        matches = [type("Match", (), {"path": path, "line": 1, "line_text": request.pattern})() for path in paths]
        return type("SearchResponse", (), {"matches": matches, "truncated": False})()

    def read(self, request):
        content = self.read_contents.get(request.path)
        if content is None:
            raise FileNotFoundError(request.path)
        return type("ReadResponse", (), {"content": content})()


class AgentTests(unittest.TestCase):
    def test_outcome_value_maps_known_names(self):
        self.assertEqual(outcome_value("OUTCOME_OK"), 1)
        self.assertEqual(outcome_value("OUTCOME_DENIED_SECURITY"), 2)

    def test_submit_response_sends_answer_request(self):
        client = FakeClient()
        response = AgentResponse(
            message="<NO>",
            outcome="OUTCOME_OK",
            grounding_refs=("/proc/catalog/x.json",),
            verified=True,
        )

        submit_response(client, response)

        self.assertEqual(len(client.requests), 1)
        request = client.requests[0]
        self.assertEqual(request.message, "<NO>")
        self.assertEqual(request.outcome, 1)
        self.assertEqual(list(request.refs), ["/proc/catalog/x.json"])

    def test_parse_catalogue_count_kind_from_current_samples(self):
        self.assertEqual(
            parse_catalogue_count_kind(
                "For the catalogue count report, how many products are Work Jacket? "
                'answer pattern: "<count: %VALUE%>"'
            ),
            "Work Jacket",
        )
        self.assertEqual(
            parse_catalogue_count_kind(
                "How many products are Work Gloves in catalogue? "
                "Answer format: `<QTY: the_actual_number>`."
            ),
            "Work Gloves",
        )
        self.assertEqual(
            parse_catalogue_count_kind(
                "How many Anchor and Wall Plug products should I report today? "
                "Answer template: `<QTY: NUMBER>`"
            ),
            "Anchor and Wall Plug",
        )

    def test_format_count_answer_respects_observed_patterns(self):
        self.assertEqual(
            format_count_answer(
                'For the catalogue count report. answer pattern: "<count: %VALUE%>"',
                11,
            ),
            "<count: 11>",
        )
        self.assertEqual(
            format_count_answer(
                "How many products are Work Gloves in catalogue? Answer format: `<QTY: the_actual_number>`.",
                12,
            ),
            "<QTY: 12>",
        )
        self.assertEqual(
            format_count_answer(
                'answer pattern: "[COUNT:%VALUE%]"',
                8,
            ),
            "[COUNT:8]",
        )
        self.assertEqual(
            format_count_answer(
                "Answer template: `<QTY: NUMBER>`",
                8,
            ),
            "<QTY: 8>",
        )

    def test_parse_catalogue_reporting_update_extracts_kind_id_and_city_scope(self):
        update = parse_catalogue_reporting_update(
            "/docs/policy-updates/2024-07-17-catalogue-reporting-anchors-plugs-brno.md",
            """# Catalogue Count Reporting Update

Requested product kind: Anchor and Wall Plug
Requested kind_id: anchors_plugs

For today's count report, count only catalogue SKUs for the requested product
kind that have at least one current inventory row in an open PowerTool store in
Brno with available_today greater than 0. Count each SKU once even if it is
available in multiple Brno branches.
""",
        )

        self.assertIsNotNone(update)
        self.assertEqual(update.kind_id, "anchors_plugs")
        self.assertEqual(update.city, "Brno")
        self.assertEqual(update.ref, "/docs/policy-updates/2024-07-17-catalogue-reporting-anchors-plugs-brno.md")

    def test_solve_task_counts_catalogue_kind_with_sql(self):
        client = FakeClient()
        response = solve_task(
            client,
            "For the catalogue count report, how many products are Work Jacket? "
            'answer pattern: "<count: %VALUE%>"',
        )

        self.assertEqual(response.message, "<count: 7>")
        self.assertEqual(response.outcome, "OUTCOME_OK")
        self.assertTrue(response.verified)
        self.assertEqual(len(client.exec_requests), 1)
        sql_request = client.exec_requests[0]
        self.assertEqual(sql_request.path, "/bin/sql")
        self.assertIn("product_kinds", sql_request.stdin)
        self.assertIn("Work Jacket", sql_request.stdin)

    def test_solve_task_applies_catalogue_reporting_update_scope(self):
        client = FakeClient()
        client.search_paths = {
            "--tmpdir": [],
            "catalogue count Anchor and Wall Plug": [],
            "Anchor and Wall Plug": ["/docs/policy-updates/2024-07-17-catalogue-reporting-anchors-plugs-brno.md"],
        }
        client.read_contents = {
            "/docs/policy-updates/2024-07-17-catalogue-reporting-anchors-plugs-brno.md": (
                "Requested kind_id: anchors_plugs\n"
                "For today's count report, count only catalogue SKUs for the requested product kind "
                "that have at least one current inventory row in an open PowerTool store in Brno "
                "with available_today greater than 0. Count each SKU once."
            )
        }

        response = solve_task(
            client,
            'How many products are Anchor and Wall Plug in catalogue? Answer format: `<QTY:%VALUE%>`.',
        )

        self.assertEqual(response.message, "<QTY:7>")
        sql = next(request for request in client.exec_requests if request.path == "/bin/sql").stdin
        self.assertIn("COUNT(DISTINCT p.sku)", sql)
        self.assertIn("JOIN inventory i ON i.sku = p.sku", sql)
        self.assertIn("JOIN stores s ON s.id = i.store_id", sql)
        self.assertIn("p.kind_id = 'anchors_plugs'", sql)
        self.assertIn("s.city = 'Brno'", sql)
        self.assertIn("i.available_today > 0", sql)
        self.assertIn("/docs/policy-updates/2024-07-17-catalogue-reporting-anchors-plugs-brno.md", response.grounding_refs)

    def test_solve_task_uses_dynamic_sql_incident_tmpdir_and_ref(self):
        client = FakeClient()
        client.search_paths = {"--tmpdir": ["/docs/urgent-sql-incident.md"]}
        client.read_contents = {
            "/docs/urgent-sql-incident.md": "Run SQL queries with: /bin/sql --tmpdir /work/tmp '<query>'"
        }

        response = solve_task(
            client,
            'How many products are Work Gloves in catalogue? Answer format: `<QTY:%VALUE%>`.',
        )

        sql_request = next(request for request in client.exec_requests if request.path == "/bin/sql")
        self.assertEqual(list(sql_request.args), ["--tmpdir", "/work/tmp"])
        self.assertIn("/docs/urgent-sql-incident.md", response.grounding_refs)

    def test_solve_task_cites_security_and_checkout_for_ambiguous_my_basket_checkout(self):
        client = FakeClient()

        response = solve_task(
            client,
            "Hi, I think I have a couple of baskets still open and I cannot find the basket number. "
            "Could you put through the one I started most recently?",
        )

        self.assertEqual(response.outcome, "OUTCOME_NONE_UNSUPPORTED")
        self.assertEqual(response.grounding_refs, ("/docs/security.md", "/docs/checkout.md"))

    def test_solve_task_handles_newest_open_basket_wording(self):
        client = FakeClient()
        client.identity_stdout = "user: cust_085\nroles: customer\n"
        client.checkout_exit_code = 1
        client.search_paths = {
            "cust_085": [
                "/proc/baskets/basket_018.json",
                "/proc/baskets/basket_019.json",
            ],
        }
        client.read_contents = {
            "/proc/baskets/basket_018.json": (
                '{"id":"basket_018","customer_id":"cust_085","status":"active",'
                '"created_at":"2021-07-25T14:03:43Z"}'
            ),
            "/proc/baskets/basket_019.json": (
                '{"id":"basket_019","customer_id":"cust_085","status":"active",'
                '"created_at":"2021-08-01T14:03:43Z"}'
            ),
        }

        response = solve_task(
            client,
            "I am trying to finish my order but I do not have the basket ID in front of me. "
            "Please use the newest open basket on my account and check it out if it is really ready today.",
        )

        self.assertEqual(response.outcome, "OUTCOME_NONE_UNSUPPORTED")
        self.assertEqual(
            response.grounding_refs,
            ("/docs/security.md", "/docs/checkout.md", "/proc/baskets/basket_019.json"),
        )

    def test_solve_task_checks_out_when_newest_basket_inventory_is_available(self):
        client = FakeClient()
        client.identity_stdout = "user: cust_085\nroles: customer\n"
        client.search_paths = {"cust_085": ["/proc/baskets/basket_019.json"]}
        client.read_contents = {
            "/proc/baskets/basket_019.json": (
                '{"id":"basket_019","customer_id":"cust_085","status":"active",'
                '"store_id":"store_brno_veveri","created_at":"2021-08-01T14:03:43Z",'
                '"lines":[{"sku":"ABC","quantity":2}]}'
            )
        }
        client.sql_outputs = ["available_today\n5\n"]

        response = solve_task(
            client,
            "I am trying to finish my order but I do not have the basket ID in front of me. "
            "Please use the newest open basket on my account and check it out if it is really ready today.",
        )

        self.assertEqual(response.outcome, "OUTCOME_OK")
        self.assertIn("basket_019", response.message)
        checkout_request = next(request for request in client.exec_requests if request.path == "/bin/checkout")
        self.assertEqual(list(checkout_request.args), ["basket_019"])
        inventory_request = next(request for request in client.exec_requests if request.path == "/bin/sql")
        self.assertIn('store_id = "store_brno_veveri"', inventory_request.stdin)
        self.assertIn('sku = "ABC"', inventory_request.stdin)

    def test_solve_task_does_not_checkout_when_selected_basket_inventory_is_short(self):
        client = FakeClient()
        client.identity_stdout = "user: cust_085\nroles: customer\n"
        client.search_paths = {"cust_085": ["/proc/baskets/basket_019.json"]}
        client.read_contents = {
            "/proc/baskets/basket_019.json": (
                '{"id":"basket_019","customer_id":"cust_085","status":"active",'
                '"store_id":"store_brno_veveri","created_at":"2021-08-01T14:03:43Z",'
                '"lines":[{"sku":"ABC","quantity":6}]}'
            )
        }
        client.sql_outputs = ["available_today\n5\n"]

        response = solve_task(
            client,
            "I am trying to finish my order but I do not have the basket ID in front of me. "
            "Please use the newest open basket on my account and check it out if it is really ready today.",
        )

        self.assertEqual(response.outcome, "OUTCOME_NONE_UNSUPPORTED")
        self.assertFalse(any(request.path == "/bin/checkout" for request in client.exec_requests))

    def test_solve_task_falls_back_when_documented_work_tmp_is_unavailable(self):
        client = FakeClient()
        client.exec_failures = ["sql: stat /work/tmp/mount.txt: no such path or path is not a mount path"]

        response = solve_task(
            client,
            "How many products are Work Gloves in catalogue? Answer format: `<QTY:%VALUE%>`.",
        )

        self.assertEqual(response.message, "<QTY:7>")
        self.assertEqual(response.outcome, "OUTCOME_OK")
        self.assertEqual(len(client.exec_requests), 2)
        self.assertEqual(list(client.exec_requests[1].args), [])

    def test_sql_tmpdir_args_uses_documented_work_tmp_first(self):
        self.assertEqual(sql_tmpdir_args(0), ["--tmpdir", "/work/tmp"])
        self.assertEqual(sql_tmpdir_args(1), [])
        self.assertEqual(sql_tmpdir_args(2), ["--tmpdir", "/tmp/mount"])

    def test_solve_task_cites_sql_scratch_note_when_work_tmp_is_used(self):
        client = FakeClient()

        response = solve_task(
            client,
            'For the catalogue count report, how many products are Work Jacket? answer pattern: "<count: NUMBER>"',
        )

        self.assertEqual(response.outcome, "OUTCOME_OK")
        self.assertEqual(list(client.exec_requests[0].args), ["--tmpdir", "/work/tmp"])
        self.assertIn(
            "/docs/current-updates/2024-07-17-sql-scratch-space.md",
            response.grounding_refs,
        )

    def test_solve_task_cites_catalogue_count_policy_note_when_found(self):
        client = FakeClient()
        client.search_paths = {
            "catalogue count Work Jacket": [],
            "Work Jacket": ["/docs/ops-policy-notes/catalogue-count-work-jacket-2024-07-17.md"],
        }

        response = solve_task(
            client,
            "For the catalogue count report, how many products are Work Jacket? "
            'answer pattern: "<count: NUMBER>"',
        )

        self.assertEqual(response.message, "<count: 7>")
        self.assertEqual(
            response.grounding_refs,
            (
                "/docs/current-updates/2024-07-17-sql-scratch-space.md",
                "/docs/ops-policy-notes/catalogue-count-work-jacket-2024-07-17.md",
            ),
        )
        self.assertEqual(client.search_requests[0].root, "/docs")
        self.assertGreaterEqual(len(client.search_requests), 2)


if __name__ == "__main__":
    unittest.main()
