"""Unit tests for the modular OOP I/O Manager components.
All tests run offline without network access, live Telegram tokens, or Supabase calls.
"""
import io
import unittest
from unittest.mock import MagicMock, patch

from io_manager_modules import (
    PRIORITY_WEIGHTS,
    BaseIOManager,
    BridgeStorageError,
    TelegramDataBridge,
    TelegramFormatter,
    TelegramIOManager,
    TelegramKeyboards,
    TelegramSessionStore,
    TelegramValidator,
)


class TestBaseIOManagerInheritance(unittest.TestCase):
    """Verifies BaseIOManager abstract contract and TelegramIOManager polymorphism."""

    def test_base_io_manager_cannot_be_instantiated_directly(self):
        with self.assertRaises(TypeError):
            BaseIOManager()  # type: ignore[abstract]

    def test_telegram_io_manager_implements_base_contract_and_di(self):
        self.assertTrue(issubclass(TelegramIOManager, BaseIOManager))
        validator = TelegramValidator()
        store = TelegramSessionStore()
        bridge = TelegramDataBridge(use_cloud=False, validator=validator)

        with patch("io_manager_modules.io_manager_telegram._TELEBOT_AVAILABLE", False):
            tg = TelegramIOManager(
                token="123456:TEST_TOKEN",
                use_cloud=False,
                validator=validator,
                session_store=store,
                data_bridge=bridge,
            )

        self.assertIsInstance(tg, BaseIOManager)
        self.assertIs(tg._validator, validator)
        self.assertIs(tg._session_store, store)
        self.assertIs(tg._bridge, bridge)

        with patch("sys.stdout", new=io.StringIO()):
            tg.display_message("Server started")
            tg.display_error("Minor warning")
            tg.display_success("Completed")
            res = tg.display_screening_results(
                [{"file": "a.pdf", "score": 90.0}, {"file": "b.pdf", "score": 80.0}],
                top_n=1,
            )
            self.assertEqual(len(res), 1)

        inputs = tg.get_employer_inputs()
        self.assertIn("company_name", inputs)
        self.assertIn("business_rules", inputs)
        self.assertEqual(inputs["top_n"], 3)


class TestTelegramValidator(unittest.TestCase):
    """Verifies rule validation, priority-weight mapping, auth validation, and Top-N capping."""

    def test_validate_and_normalize_rule_assigns_weights(self):
        for prio, expected_w in PRIORITY_WEIGHTS.items():
            res = TelegramValidator.validate_and_normalize_rule("Must know Python", prio.upper())
            self.assertEqual(res["priority"], prio)
            self.assertEqual(res["weight"], expected_w)
            self.assertEqual(res["text"], "Must know Python")

    def test_validate_and_normalize_rule_rejects_short_or_invalid_priority(self):
        with self.assertRaises(ValueError):
            TelegramValidator.validate_and_normalize_rule("Hi", "must")
        with self.assertRaises(ValueError):
            TelegramValidator.validate_and_normalize_rule("Valid rule text", "critical")

    def test_normalize_rules_list_lenient_vs_strict(self):
        raw = [
            {"text": "Python backend", "priority": "must"},
            {"text": "", "priority": "nice"},
            {"text": "Invalid prio rule", "priority": "unknown"},
            "bad-item",
        ]
        lenient = TelegramValidator.normalize_rules_list(raw, strict=False)
        self.assertEqual(len(lenient), 2)
        self.assertEqual(lenient[1]["priority"], "reject")
        self.assertEqual(lenient[1]["weight"], 0)

        with self.assertRaises(ValueError):
            TelegramValidator.normalize_rules_list(raw, strict=True)

    def test_auth_and_set_name_validation_helpers(self):
        self.assertEqual(TelegramValidator.validate_set_name("  Backend Dev  "), "Backend Dev")
        with self.assertRaises(ValueError):
            TelegramValidator.validate_set_name("A")

        self.assertEqual(TelegramValidator.validate_company_name("  Acme  "), "Acme")
        with self.assertRaises(ValueError):
            TelegramValidator.validate_company_name("X")

        self.assertEqual(TelegramValidator.validate_passcode("1234"), "1234")
        with self.assertRaises(ValueError):
            TelegramValidator.validate_passcode("123")

        hashed = TelegramValidator.hash_passcode("secret")
        self.assertTrue(TelegramValidator.verify_passcode("secret", hashed))
        self.assertFalse(TelegramValidator.verify_passcode("wrong", hashed))

        code = TelegramValidator.generate_invite_code("Acme Tech")
        self.assertTrue(code.startswith("ACME-"))

    def test_cap_top_n(self):
        self.assertEqual(TelegramValidator.cap_top_n(10, 3), (3, True))
        self.assertEqual(TelegramValidator.cap_top_n(2, 3), (2, False))
        self.assertEqual(TelegramValidator.cap_top_n(5, 0), (5, False))
        self.assertEqual(TelegramIOManager._cap_top_n(150, 0), (100, False))


class TestTelegramSessionStore(unittest.TestCase):
    """Verifies per-chat session isolation, active company state, and Top-N syncing."""

    def setUp(self):
        self.store = TelegramSessionStore(default_top_n=3)

    def test_session_isolation_and_pending_rule_text(self):
        self.store.set_top_n(111, 5)
        self.store.set_pending_rule_text(111, "Knows Docker")
        self.assertEqual(self.store.get_top_n(111), 5)
        self.assertEqual(self.store.get_pending_rule_text(111), "Knows Docker")

        # Separate chat has default state
        self.assertEqual(self.store.get_top_n(222), 3)
        self.assertIsNone(self.store.get_pending_rule_text(222))

    def test_get_effective_top_n_caps_and_updates_session(self):
        self.store.set_top_n(111, 10)
        self.assertEqual(self.store.get_effective_top_n(111, resume_count=2), 2)
        self.assertEqual(self.store.get_top_n(111), 2)

    def test_active_company_tracking(self):
        self.store.set_active_company_name(999, "Acme Corp")
        self.assertEqual(self.store.get_active_company_name(999), "Acme Corp")
        self.store.clear_active_company(999)
        self.assertIsNone(self.store.get_active_company_name(999))


class TestTelegramDataBridge(unittest.TestCase):
    """Verifies stub & cloud-delegated persistence inside TelegramDataBridge."""

    def test_stub_company_rules_resumes_and_scoped_results(self):
        bridge = TelegramDataBridge(use_cloud=False)

        comp = bridge.create_company("Acme Tech", "hash", owner_id=10, invite_code="ACME-1234")
        cid = comp["company_id"]
        self.assertIsNotNone(bridge.get_company_by_invite("acme-1234"))
        bridge.add_company_member(cid, "Acme Tech", 20)
        name, info = bridge.resolve_user_company(20)
        self.assertEqual(name, "Acme Tech")
        self.assertIn(20, info["members"])

        # Multi-set CRUD
        rs1 = bridge.create_rule_set(cid, "Backend", [{"text": "Python skill", "priority": "must"}])
        rs2 = bridge.create_rule_set(cid, "Data", [{"text": "SQL queries", "priority": "important"}])
        self.assertEqual(bridge.get_active_rule_set(cid)["rule_set_id"], rs2["rule_set_id"])
        bridge.set_active_rule_set(cid, rs1["rule_set_id"])
        self.assertEqual(bridge.get_active_rule_set(cid)["set_name"], "Backend")

        updated = bridge.update_rule_set(cid, rs1["rule_set_id"], set_name="Backend Eng")
        self.assertEqual(updated["set_name"], "Backend Eng")

        # Results scoped per rule set
        bridge.save_screening_results(
            cid,
            [{"file": "alice.pdf", "score": 92.0}],
            {"totals": {"processed": 1}},
            business_rules_id=rs1["rule_set_id"],
        )
        r_set1, s_set1 = bridge.get_screening_results(cid, business_rules_id=rs1["rule_set_id"])
        r_set2, s_set2 = bridge.get_screening_results(cid, business_rules_id=rs2["rule_set_id"])
        self.assertEqual(len(r_set1), 1)
        self.assertIsNotNone(s_set1)
        self.assertEqual(r_set2, [])
        self.assertIsNone(s_set2)

        self.assertTrue(bridge.delete_rule_set(cid, rs1["rule_set_id"]))
        self.assertEqual(len(bridge.list_rule_sets(cid)), 1)

    def test_cloud_delegation_forwards_to_data_manager(self):
        mock_dm = MagicMock()
        mock_dm.CLOUD_READY = True
        mock_dm.list_company_resumes.return_value = [{"file_name": "cv.pdf", "status": "valid"}]
        bridge = TelegramDataBridge(data_manager=mock_dm, use_cloud=True)

        resumes = bridge.list_resumes(company_id=7)
        self.assertEqual(len(resumes), 1)
        mock_dm.list_company_resumes.assert_called_once_with(7)


class TestTelegramFormatterAndKeyboards(unittest.TestCase):
    """Verifies Telegram Bot HTML formatting and inline keyboard generation."""

    def test_format_dashboard_contains_company_metadata(self):
        text = TelegramFormatter.format_dashboard(
            company_name="Acme Corp",
            invite_code="ACME-1234",
            company_id=101,
            resume_count=5,
        )
        self.assertIn("Acme Corp", text)
        self.assertIn("ACME-1234", text)
        self.assertIn("#101", text)
        self.assertIn("5 PDF(s)", text)

    def test_format_results_overview(self):
        ranked = [
            {"name": "Alice", "score": 90.5, "reason": "Strong match"},
            {"name": "Bob", "score": 80.0, "reason": "Good match"},
        ]
        text = TelegramFormatter.format_results_overview("Acme Corp", ranked)
        self.assertIn("Alice", text)
        self.assertIn("90.5%", text)
        self.assertIn("Bob", text)
        self.assertIn("80.0%", text)

    def test_format_ai_summary_json_renders_all_fields(self):
        summary_data = {
            "totals": {"processed": 5, "scored": 4, "rejected": 1, "invalid": 0},
            "score_statistics": {"average": 85.0, "highest": 95.0, "lowest": 75.0},
            "rule_statistics": [
                {"rule": "Must know SQL", "priority": "must", "met": 4, "missed": 0, "percent_met": 100.0}
            ],
            "top_candidates": [
                {"rank": 1, "name": "Alice", "score": 95.0, "reason": "Matched all rules"}
            ],
            "overall_summary": "Excellent talent pool.",
        }
        text = TelegramFormatter.format_ai_summary_json("Acme Corp", summary_data)
        self.assertIn("RESUM-AI SUMMARY REPORT (Acme Corp)", text)
        self.assertIn("Excellent talent pool.", text)
        self.assertIn("Total Resumes: <b>5</b>", text)
        self.assertIn("Must know SQL", text)
        self.assertIn("Alice", text)

    def test_keyboards_generate_valid_markups(self):
        auth_kb = TelegramKeyboards.auth_menu()
        self.assertIsNotNone(auth_kb.keyboard)
        self.assertEqual(len(auth_kb.keyboard), 2)

        dash_kb = TelegramKeyboards.dashboard_menu()
        self.assertIsNotNone(dash_kb.keyboard)
        self.assertGreaterEqual(len(dash_kb.keyboard), 4)

        results_kb = TelegramKeyboards.results_menu(ranked_count=3)
        self.assertIsNotNone(results_kb.keyboard)

    def test_top_n_menu_caps_presets_to_max_resumes(self):
        kb_3 = TelegramKeyboards.top_n_menu(current_top_n=3, max_resumes=3)
        callbacks_3 = [btn.callback_data for row in kb_3.keyboard for btn in row]
        self.assertIn("set_topn:1", callbacks_3)
        self.assertIn("set_topn:3", callbacks_3)
        self.assertNotIn("set_topn:5", callbacks_3)
        self.assertNotIn("set_topn:10", callbacks_3)

        kb_2 = TelegramKeyboards.top_n_menu(current_top_n=2, max_resumes=2)
        callbacks_2 = [btn.callback_data for row in kb_2.keyboard for btn in row]
        self.assertIn("set_topn:1", callbacks_2)
        self.assertIn("set_topn:2", callbacks_2)
        self.assertNotIn("set_topn:3", callbacks_2)


class _FakeTeleBot:
    """Minimal fake TeleBot capturing handlers and API calls for offline error-handling tests."""

    def __init__(self, token: str, parse_mode: str = "HTML"):
        self.token = token
        self.parse_mode = parse_mode
        self.callback_handler = None
        self.document_handler = None
        self.sent_messages = []
        self.replies = []
        self.edited_messages = []
        self.send_message_side_effect = None
        self.answer_callback_side_effect = None
        self.get_file_side_effect = None
        self.send_document_side_effect = None
        self.infinity_polling_side_effect = None

    def message_handler(self, commands=None, content_types=None):
        def decorator(fn):
            if content_types and "document" in content_types:
                self.document_handler = fn
            return fn

        return decorator

    def callback_query_handler(self, func=None):
        def decorator(fn):
            self.callback_handler = fn
            return fn

        return decorator

    def send_message(self, chat_id, text, **kwargs):
        if self.send_message_side_effect is not None:
            effect = self.send_message_side_effect
            if callable(effect):
                effect(chat_id, text, **kwargs)
            else:
                raise effect
        self.sent_messages.append((chat_id, text, kwargs))
        return MagicMock(message_id=len(self.sent_messages))

    def reply_to(self, message, text, **kwargs):
        self.replies.append((message, text, kwargs))
        return MagicMock(message_id=100 + len(self.replies))

    def edit_message_text(self, text, chat_id=None, message_id=None, **kwargs):
        self.edited_messages.append((chat_id, message_id, text, kwargs))

    def answer_callback_query(self, call_id):
        if self.answer_callback_side_effect is not None:
            raise self.answer_callback_side_effect

    def get_file(self, file_id):
        if self.get_file_side_effect is not None:
            raise self.get_file_side_effect
        return MagicMock(file_path="resumes/sample.pdf")

    def download_file(self, file_path):
        return b""

    def send_document(self, chat_id, bio, **kwargs):
        if self.send_document_side_effect is not None:
            raise self.send_document_side_effect

    def register_next_step_handler(self, msg, callback, *args):
        pass

    def infinity_polling(self, **kwargs):
        if self.infinity_polling_side_effect is not None:
            raise self.infinity_polling_side_effect


class TestTelegramErrorHandling(unittest.TestCase):
    """Verifies API failure, bad input, and corrupt/invalid file error handling across io_manager_modules."""

    def _build_tg(self, bridge=None):
        fake_module = MagicMock()
        fake_module.TeleBot.side_effect = _FakeTeleBot
        with (
            patch("io_manager_modules.io_manager_telegram._TELEBOT_AVAILABLE", True),
            patch("io_manager_modules.io_manager_telegram.telebot", fake_module),
        ):
            return TelegramIOManager(
                token="123456:TEST_TOKEN",
                use_cloud=False,
                data_bridge=bridge,
            )

    def test_validator_callback_int_and_invalid_topn(self):
        self.assertEqual(TelegramValidator.parse_callback_int("res_del:3"), 3)
        with self.assertRaises(ValueError):
            TelegramValidator.parse_callback_int("res_del_no_colon")
        with self.assertRaises(ValueError):
            TelegramValidator.parse_callback_int("res_del:not_an_int")
        with self.assertRaises(ValueError):
            TelegramValidator.cap_top_n("bad", 5)

    def test_bridge_normalizes_cloud_failures_and_corrupt_or_empty_pdfs(self):
        mock_dm = MagicMock()
        mock_dm.CLOUD_READY = True
        mock_dm.list_company_resumes.side_effect = ConnectionError("Supabase timeout")
        mock_dm.parse_pdf_bytes.side_effect = RuntimeError("Corrupt XRef stream")
        bridge = TelegramDataBridge(data_manager=mock_dm, use_cloud=True)

        with self.assertRaises(BridgeStorageError) as ctx:
            bridge.list_resumes(1)
        self.assertIn("Supabase timeout", str(ctx.exception))

        empty_res = bridge.parse_pdf_bytes_in_memory("empty.pdf", b"")
        self.assertEqual(empty_res["status"], "invalid")
        self.assertIn("empty", empty_res["reason"].lower())

        corrupt_res = bridge.parse_pdf_bytes_in_memory("bad.pdf", b"%PDF-corrupt")
        self.assertEqual(corrupt_res["status"], "invalid")
        self.assertIn("Corrupt XRef stream", corrupt_res["reason"])

    def test_send_safe_html_chunks_long_lines_and_falls_back_to_plain_text(self):
        tg = self._build_tg()

        def fail_html_only(chat_id, text, **kwargs):
            if kwargs.get("parse_mode") is not None or "parse_mode" not in kwargs:
                raise RuntimeError("Bad Request: can't parse entities")

        tg._bot.send_message_side_effect = fail_html_only
        long_line = "<b>" + ("A" * 4100) + "</b>"
        with patch("sys.stdout", new=io.StringIO()):
            tg._send_safe_html(99, long_line)

        self.assertEqual(len(tg._bot.sent_messages), 2)
        for _, sent_text, kwargs in tg._bot.sent_messages:
            self.assertIsNone(kwargs.get("parse_mode"))
            self.assertNotIn("<b>", sent_text)

    def test_callback_handler_catches_malformed_payload_and_bridge_error(self):
        bridge = MagicMock()
        bridge.use_cloud = False
        bridge.resolve_user_company.return_value = ("Acme", {"company_id": 1})
        bridge.list_resumes.side_effect = BridgeStorageError("DB connection lost")
        tg = self._build_tg(bridge=bridge)

        bad_call = MagicMock()
        bad_call.id = "cb1"
        bad_call.message.chat.id = 55
        bad_call.from_user.id = 10
        bad_call.data = "res_del:not_a_number"
        tg._bot.answer_callback_side_effect = RuntimeError("query is too old")

        with patch("sys.stdout", new=io.StringIO()):
            tg._bot.callback_handler(bad_call)
            bad_call.data = "menu_resumes"
            tg._bot.callback_handler(bad_call)

        texts = [m[1] for m in tg._bot.sent_messages]
        self.assertTrue(any("Action failed" in t and "Invalid numeric selection" in t for t in texts))
        self.assertTrue(any("Action failed" in t and "DB connection lost" in t for t in texts))

    def test_pdf_upload_rejects_oversized_and_handles_download_error(self):
        bridge = TelegramDataBridge(use_cloud=False)
        comp = bridge.create_company("Acme", "hash", 10, "ACME-1111")
        tg = self._build_tg(bridge=bridge)
        tg._session_store.set_active_company_name(10, comp["company_name"])

        oversized_msg = MagicMock()
        oversized_msg.chat.id = 55
        oversized_msg.from_user.id = 10
        oversized_msg.document = MagicMock(file_name="huge.pdf", file_size=21 * 1024 * 1024, file_id="f1")
        tg._bot.document_handler(oversized_msg)
        self.assertTrue(any("20 MB" in r[1] for r in tg._bot.replies))

        fail_msg = MagicMock()
        fail_msg.chat.id = 55
        fail_msg.from_user.id = 10
        fail_msg.document = MagicMock(file_name="cv.pdf", file_size=1024, file_id="f2")
        tg._bot.get_file_side_effect = RuntimeError("Telegram network timeout")
        with patch("sys.stdout", new=io.StringIO()):
            tg._bot.document_handler(fail_msg)
        self.assertTrue(any("Upload failed" in e[2] for e in tg._bot.edited_messages))

    def test_step_handlers_and_candidate_pdf_handle_cloud_and_api_errors(self):
        bridge = MagicMock()
        bridge.use_cloud = False
        bridge.create_rule_set.side_effect = BridgeStorageError("Cloud write failed")
        bridge.update_rule_set.side_effect = BridgeStorageError("Cloud update failed")
        bridge.get_company_by_invite.side_effect = BridgeStorageError("Invite query failed")
        bridge.list_rule_sets.return_value = []
        bridge.get_active_rule_set.return_value = {
            "rule_set_id": 1,
            "set_name": "Default",
            "rules": [{"text": "Knows Python", "priority": "must", "weight": 4}],
        }
        bridge.set_active_rule_set.return_value = bridge.get_active_rule_set.return_value
        bridge.get_screening_results.return_value = ([{"file": "alice.pdf", "score": 95}], None)
        bridge.get_resume_pdf_bytes.return_value = b"%PDF-1.4"
        bridge.list_resumes.return_value = []

        tg = self._build_tg(bridge=bridge)
        tg._bot.send_document_side_effect = RuntimeError("Upload blocked")

        msg = MagicMock()
        msg.chat.id = 55
        msg.from_user.id = 10
        msg.text = "Backend Team"

        with patch("sys.stdout", new=io.StringIO()):
            tg._step_create_ruleset_name(msg, "Acme", 1)
            tg._step_rename_ruleset(msg, "Acme", 1, 1)
            tg._step_edit_rule_text(msg, "Acme", 1, 1, 1)
            tg._step_join_company_code(msg)
            tg._send_candidate_pdf(55, "Acme", 1, 1)

        reply_texts = [r[1] for r in tg._bot.replies]
        sent_texts = [m[1] for m in tg._bot.sent_messages]
        self.assertTrue(any("Could not create Rule Set" in t for t in reply_texts))
        self.assertTrue(any("Could not rename Rule Set" in t for t in reply_texts))
        self.assertTrue(any("Could not update rule" in t for t in reply_texts))
        self.assertTrue(any("Invite lookup failed" in t for t in reply_texts))
        self.assertTrue(any("not found in storage" in t for t in sent_texts))

    def test_start_wraps_unexpected_polling_failure(self):
        tg = self._build_tg()
        tg._bot.infinity_polling_side_effect = RuntimeError("401 Unauthorized")
        with patch("sys.stdout", new=io.StringIO()), self.assertRaises(RuntimeError) as ctx:
            tg.start()
        self.assertIn("Telegram polling failed", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
