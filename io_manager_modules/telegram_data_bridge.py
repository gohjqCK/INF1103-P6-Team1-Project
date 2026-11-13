"""Cloud-ready DataManager bridge with thread-safe in-memory stub fallback."""
import io
import threading
from typing import Any, Dict, List, Optional, Tuple

from io_manager_modules.telegram_validator import TelegramValidator

try:
    import pypdf
    _PYPDF_AVAILABLE = True
except ImportError:
    pypdf = None
    _PYPDF_AVAILABLE = False


class TelegramDataBridge:
    """Encapsulates company, rule-set, resume, and results persistence for TelegramIOManager."""

    def __init__(
        self,
        data_manager: Optional[Any] = None,
        use_cloud: Optional[bool] = None,
        validator: Optional[TelegramValidator] = None,
    ):
        self._data_manager = data_manager
        self._use_cloud = (
            bool(getattr(data_manager, "CLOUD_READY", False))
            if use_cloud is None
            else bool(use_cloud)
        )
        self._validator = validator or TelegramValidator()

        # Thread-safe in-memory caches and stub stores (used when cloud DataManager is unavailable)
        self._lock = threading.RLock()
        self._next_stub_company_id = 101
        self._next_stub_ruleset_id = 201
        self._companies: Dict[str, Dict[str, Any]] = {}
        self._company_rule_sets: Dict[int, List[Dict[str, Any]]] = {}
        self._company_active_ruleset: Dict[int, int] = {}
        self._company_resumes: Dict[int, List[Dict[str, Any]]] = {}
        self._company_results: Dict[Tuple[int, int], List[Dict[str, Any]]] = {}
        self._company_summaries: Dict[Tuple[int, int], Dict[str, Any]] = {}
        self._company_filtered_resumes: Dict[Tuple[int, int], Dict[str, Any]] = {}

    @property
    def use_cloud(self) -> bool:
        return self._use_cloud

    def _cloud_has(self, method_name: str) -> bool:
        return (
            self._use_cloud
            and self._data_manager is not None
            and hasattr(self._data_manager, method_name)
        )

    # ---- Companies & Membership ----

    def create_company(
        self,
        name: str,
        passcode_hash: str,
        owner_id: int,
        invite_code: str,
    ) -> Dict[str, Any]:
        """Creates a new company record in Supabase or stub store."""
        if self._cloud_has("create_company"):
            record = self._data_manager.create_company(
                company_name=name,
                passcode_hash=passcode_hash,
                owner_id=owner_id,
                invite_code=invite_code,
            )
            with self._lock:
                self._companies[record["company_name"]] = record
            return record

        with self._lock:
            for existing_name in self._companies:
                if existing_name.lower() == name.lower():
                    raise ValueError(f"Company '{existing_name}' already exists.")

            comp_id = self._next_stub_company_id
            self._next_stub_company_id += 1
            record = {
                "company_id": comp_id,
                "company_name": name,
                "invite_code": invite_code,
                "passcode_hash": passcode_hash,
                "owner": owner_id,
                "members": [owner_id],
            }
            self._companies[name] = record
            self._company_rule_sets.setdefault(comp_id, [])
            self._company_resumes.setdefault(comp_id, [])
            return dict(record)

    def get_company_by_invite(self, invite_code: str) -> Optional[Dict[str, Any]]:
        """Fetches a company record by case-insensitive invite code."""
        code = invite_code.strip().upper()
        if self._cloud_has("get_company_by_invite"):
            record = self._data_manager.get_company_by_invite(code)
            if record:
                with self._lock:
                    self._companies[record["company_name"]] = record
            return record

        with self._lock:
            for record in self._companies.values():
                if str(record.get("invite_code", "")).upper() == code:
                    return dict(record)
        return None

    def add_company_member(self, company_id: int, comp_name: str, user_id: int) -> None:
        """Adds user_id as a member of company_id."""
        if self._cloud_has("add_company_member"):
            self._data_manager.add_company_member(company_id=company_id, user_id=user_id)

        with self._lock:
            if comp_name in self._companies:
                members = self._companies[comp_name].setdefault("members", [])
                if user_id not in members:
                    members.append(user_id)

    def resolve_user_company(
        self,
        user_id: int,
        active_name: Optional[str] = None,
    ) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """Resolves a user's active company record from active_name or membership list."""
        with self._lock:
            if active_name and active_name in self._companies:
                return active_name, self._companies[active_name]
            for name, info in self._companies.items():
                if user_id == info.get("owner") or user_id in info.get("members", []):
                    return name, info
        return None, None

    def get_default_company_inputs(self) -> Tuple[str, int, Optional[Dict[str, Any]], List[Dict[str, Any]]]:
        """Returns default company details and active rule set for BaseIOManager.get_employer_inputs."""
        with self._lock:
            comp_name = next(iter(self._companies), "General")
            comp_info = self._companies.get(comp_name, {})
            comp_id = comp_info.get("company_id", 101)
            active_set = self.get_active_rule_set(comp_id)
            rules = active_set.get("rules", []) if active_set else []
            return comp_name, comp_id, active_set, rules

    # ---- Multi-Set Business Rules ----

    def list_rule_sets(self, company_id: int) -> List[Dict[str, Any]]:
        """Lists all business rule sets belonging to company_id."""
        if self._cloud_has("list_company_rule_sets"):
            sets = self._data_manager.list_company_rule_sets(company_id) or []
            return [
                {
                    "rule_set_id": rs.get("rule_set_id") or rs.get("id"),
                    "company_id": rs.get("company_id", company_id),
                    "set_name": rs.get("set_name") or "Default",
                    "rules": self._validator.normalize_rules_list(rs.get("rules")),
                }
                for rs in sets
            ]

        with self._lock:
            return [
                {
                    "rule_set_id": rs["rule_set_id"],
                    "company_id": rs["company_id"],
                    "set_name": rs["set_name"],
                    "rules": self._validator.normalize_rules_list(rs.get("rules")),
                }
                for rs in self._company_rule_sets.get(company_id, [])
            ]

    def get_active_rule_set(self, company_id: int) -> Optional[Dict[str, Any]]:
        """Returns the currently selected rule set for company_id, defaulting to the first set."""
        all_sets = self.list_rule_sets(company_id)
        if not all_sets:
            with self._lock:
                self._company_active_ruleset.pop(company_id, None)
            return None

        with self._lock:
            active_id = self._company_active_ruleset.get(company_id)
            if active_id is not None:
                for rs in all_sets:
                    if rs["rule_set_id"] == active_id:
                        return rs
            self._company_active_ruleset[company_id] = all_sets[0]["rule_set_id"]
            return all_sets[0]

    def set_active_rule_set(self, company_id: int, rule_set_id: int) -> Optional[Dict[str, Any]]:
        """Activates rule_set_id for company_id if it exists."""
        for rs in self.list_rule_sets(company_id):
            if rs["rule_set_id"] == rule_set_id:
                with self._lock:
                    self._company_active_ruleset[company_id] = rule_set_id
                return rs
        return None

    def create_rule_set(
        self,
        company_id: int,
        set_name: str,
        rules: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Validates, creates, and activates a named rule set for company_id."""
        clean_name = self._validator.validate_set_name(set_name)
        existing = self.list_rule_sets(company_id)
        if any(rs["set_name"].lower() == clean_name.lower() for rs in existing):
            raise ValueError(f"A Rule Set named '{clean_name}' already exists for this company.")

        normalized_rules = self._validator.normalize_rules_list(rules, strict=True)

        if self._cloud_has("create_company_rule_set"):
            created = self._data_manager.create_company_rule_set(
                company_id=company_id,
                set_name=clean_name,
                rules=normalized_rules,
            )
            created_set = {
                "rule_set_id": created.get("rule_set_id") or created.get("id"),
                "company_id": created.get("company_id", company_id),
                "set_name": created.get("set_name", clean_name),
                "rules": self._validator.normalize_rules_list(created.get("rules")),
            }
            with self._lock:
                self._company_active_ruleset[company_id] = created_set["rule_set_id"]
            return created_set

        with self._lock:
            rs_id = self._next_stub_ruleset_id
            self._next_stub_ruleset_id += 1
            created_set = {
                "rule_set_id": rs_id,
                "company_id": company_id,
                "set_name": clean_name,
                "rules": normalized_rules,
            }
            self._company_rule_sets.setdefault(company_id, []).append(created_set)
            self._company_active_ruleset[company_id] = rs_id
            return dict(created_set)

    def update_rule_set(
        self,
        company_id: int,
        rule_set_id: int,
        set_name: Optional[str] = None,
        rules: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Updates a rule set's name and/or rules in place."""
        clean_name: Optional[str] = None
        if set_name is not None:
            clean_name = self._validator.validate_set_name(set_name)
            existing = self.list_rule_sets(company_id)
            if any(
                rs["rule_set_id"] != rule_set_id and rs["set_name"].lower() == clean_name.lower()
                for rs in existing
            ):
                raise ValueError(f"Another Rule Set named '{clean_name}' already exists.")

        normalized_rules = (
            self._validator.normalize_rules_list(rules, strict=True)
            if rules is not None
            else None
        )

        if self._cloud_has("update_company_rule_set"):
            updated = self._data_manager.update_company_rule_set(
                company_id=company_id,
                rule_set_id=rule_set_id,
                set_name=clean_name,
                rules=normalized_rules,
            )
            return {
                "rule_set_id": updated.get("rule_set_id") or updated.get("id") or rule_set_id,
                "company_id": updated.get("company_id", company_id),
                "set_name": updated.get("set_name") or clean_name or "Default",
                "rules": self._validator.normalize_rules_list(updated.get("rules")),
            }

        with self._lock:
            for rs in self._company_rule_sets.get(company_id, []):
                if rs["rule_set_id"] == rule_set_id:
                    if clean_name is not None:
                        rs["set_name"] = clean_name
                    if normalized_rules is not None:
                        rs["rules"] = normalized_rules
                    return {
                        "rule_set_id": rs["rule_set_id"],
                        "company_id": rs["company_id"],
                        "set_name": rs["set_name"],
                        "rules": list(rs["rules"]),
                    }
        raise ValueError(f"Rule Set #{rule_set_id} not found.")

    def delete_rule_set(self, company_id: int, rule_set_id: int) -> bool:
        """Deletes rule_set_id and re-selects the active rule set if needed."""
        if self._cloud_has("delete_company_rule_set"):
            deleted = bool(self._data_manager.delete_company_rule_set(company_id, rule_set_id))
        else:
            with self._lock:
                sets = self._company_rule_sets.get(company_id, [])
                new_sets = [rs for rs in sets if rs["rule_set_id"] != rule_set_id]
                deleted = len(new_sets) < len(sets)
                self._company_rule_sets[company_id] = new_sets

        if deleted:
            with self._lock:
                if self._company_active_ruleset.get(company_id) == rule_set_id:
                    self._company_active_ruleset.pop(company_id, None)
            self.get_active_rule_set(company_id)
        return deleted

    # ---- Resumes ----

    def parse_pdf_bytes_in_memory(self, file_name: str, pdf_bytes: bytes) -> Dict[str, Any]:
        """Parses in-memory PDF bytes via DataManager or local pypdf fallback."""
        if self._data_manager is not None and hasattr(self._data_manager, "parse_pdf_bytes"):
            resume_obj = self._data_manager.parse_pdf_bytes(file_name, pdf_bytes)
            result = resume_obj.to_dict()
            result["file_name"] = file_name
            return result

        if not _PYPDF_AVAILABLE:
            return {
                "file": file_name,
                "file_name": file_name,
                "status": "valid",
                "reason": "",
                "pages": 1,
                "text": "",
            }

        try:
            reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
            pages = len(reader.pages)
            text = "\n".join((p.extract_text() or "") for p in reader.pages).strip()
            if len(text) < 200:
                return {
                    "file": file_name,
                    "file_name": file_name,
                    "status": "invalid",
                    "reason": "No readable text (it may be a scanned image)",
                    "pages": pages,
                    "text": text,
                }
            if len(text) > 20000:
                return {
                    "file": file_name,
                    "file_name": file_name,
                    "status": "invalid",
                    "reason": f"Too long for one resume ({pages} pages)",
                    "pages": pages,
                    "text": text,
                }
            return {
                "file": file_name,
                "file_name": file_name,
                "status": "valid",
                "reason": "",
                "pages": pages,
                "text": text,
            }
        except Exception as err:
            return {
                "file": file_name,
                "file_name": file_name,
                "status": "invalid",
                "reason": f"Could not read the PDF file: {err}",
                "pages": 0,
                "text": "",
            }

    def upload_resume(
        self,
        company_id: int,
        company_name: str,
        file_name: str,
        pdf_bytes: bytes,
    ) -> Dict[str, Any]:
        """Uploads raw PDF bytes to cloud Storage or session stub store."""
        if self._cloud_has("upload_resume_bytes"):
            result = self._data_manager.upload_resume_bytes(
                file_name=file_name,
                pdf_bytes=pdf_bytes,
                company_id=company_id,
            )
            result.setdefault("file_name", file_name)
            result.setdefault("source", "Supabase Cloud")
            return result

        parsed = self.parse_pdf_bytes_in_memory(file_name, pdf_bytes)
        entry = {
            "file": file_name,
            "file_name": file_name,
            "status": parsed.get("status", "valid"),
            "reason": parsed.get("reason", ""),
            "pages": parsed.get("pages", 0),
            "text": parsed.get("text", ""),
            "pdf_bytes": pdf_bytes,
            "company_id": company_id,
            "company_name": company_name,
            "source": "Session Memory (Cloud Stub)",
        }
        with self._lock:
            bucket = self._company_resumes.setdefault(company_id, [])
            bucket = [r for r in bucket if r.get("file_name") != file_name]
            bucket.append(entry)
            self._company_resumes[company_id] = bucket
        return dict(entry)

    def list_resumes(self, company_id: int) -> List[Dict[str, Any]]:
        """Lists uploaded resumes for company_id."""
        if self._cloud_has("list_company_resumes"):
            return list(self._data_manager.list_company_resumes(company_id) or [])

        if (
            self._use_cloud
            and self._data_manager is not None
            and hasattr(self._data_manager, "db_handler")
        ):
            rows = self._data_manager.db_handler.fetch_resume_files(company_id=company_id)
            return [
                {
                    "file": row.get("file_name"),
                    "file_name": row.get("file_name"),
                    "status": row.get("status", "valid"),
                    "reason": row.get("invalid_reason", ""),
                    "pages": row.get("pages", 0),
                    "text": row.get("parsed_text", ""),
                    "pdf_url": row.get("pdf_url", ""),
                    "source": "Supabase Cloud",
                }
                for row in rows
            ]

        with self._lock:
            return [dict(r) for r in self._company_resumes.get(company_id, [])]

    def delete_resume(self, company_id: int, file_name: str) -> bool:
        """Deletes a single resume for company_id."""
        if self._cloud_has("delete_company_resume"):
            return bool(self._data_manager.delete_company_resume(company_id, file_name))

        with self._lock:
            bucket = self._company_resumes.get(company_id, [])
            new_bucket = [r for r in bucket if r.get("file_name") != file_name]
            removed = len(new_bucket) < len(bucket)
            self._company_resumes[company_id] = new_bucket
            return removed

    def clear_resumes(self, company_id: int) -> None:
        """Deletes all resumes belonging to company_id."""
        if self._cloud_has("clear_company_resumes"):
            self._data_manager.clear_company_resumes(company_id)
            return

        with self._lock:
            self._company_resumes[company_id] = []

    def get_resume_pdf_bytes(self, company_id: int, file_name: str) -> Optional[bytes]:
        """Downloads or retrieves raw PDF bytes for file_name."""
        if self._cloud_has("download_resume_bytes"):
            return self._data_manager.download_resume_bytes(company_id, file_name)

        with self._lock:
            for item in self._company_resumes.get(company_id, []):
                if item.get("file_name") == file_name:
                    return item.get("pdf_bytes")
        return None

    # ---- Scoped Screening Results & Summary ----

    @staticmethod
    def _results_key(company_id: int, business_rules_id: Optional[int]) -> Tuple[int, int]:
        return (company_id, int(business_rules_id) if business_rules_id is not None else 0)

    def save_screening_results(
        self,
        company_id: int,
        ranked_candidates: List[Dict[str, Any]],
        summary_data: Optional[Dict[str, Any]],
        filtered_resumes: Optional[Dict[str, Any]] = None,
        business_rules_id: Optional[int] = None,
    ) -> None:
        """Saves screening results and optional summary data scoped by company and rule set."""
        if self._cloud_has("save_screening_results"):
            self._data_manager.save_screening_results(
                company_id=company_id,
                ranked_candidates=ranked_candidates,
                summary_data=summary_data,
                filtered_resumes=filtered_resumes,
                business_rules_id=business_rules_id,
            )

        key = self._results_key(company_id, business_rules_id)
        with self._lock:
            self._company_results[key] = list(ranked_candidates)
            if summary_data is not None:
                self._company_summaries[key] = dict(summary_data)
            if filtered_resumes is not None:
                self._company_filtered_resumes[key] = dict(filtered_resumes)

    def get_screening_results(
        self,
        company_id: int,
        business_rules_id: Optional[int] = None,
    ) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """Retrieves latest screening results and linked AI summary for company/rule set."""
        if self._cloud_has("get_screening_results"):
            res = self._data_manager.get_screening_results(
                company_id=company_id,
                business_rules_id=business_rules_id,
            )
            if isinstance(res, tuple) and len(res) == 2:
                return res[0] or [], res[1]

        key = self._results_key(company_id, business_rules_id)
        with self._lock:
            return (
                list(self._company_results.get(key, [])),
                self._company_summaries.get(key),
            )

