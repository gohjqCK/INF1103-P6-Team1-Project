# Handles API connectivity and queries for Supabase DB
import os
import re
from typing import List, Dict, Any, Optional, Tuple
from supabase import Client, create_client
from data_manager_modules.data_manager_resume import Resume


class SupabaseHandler:
    # Handles database transactions with Supabase

    STORAGE_BUCKET = "resume_files"


    def __init__(self, url: Optional[str] = None, key: Optional[str] = None):
        self.url = url or os.getenv("SUPABASE_URL", "https://gkrrffsbedfodcnnvhys.supabase.co")
        self.key = key or os.getenv("SUPABASE_KEY", "sb_publishable_-_fcFwwIF60dlOMaC_9xMQ_YFX98Q6D")
        self.client: Client = create_client(self.url, self.key)

# -----------------------------------------------------------------
# Functions to handle company + users creation to supabase
# -----------------------------------------------------------------

    def _ensure_user_exists(self, telegram_user_id: int) -> int:
        """Upserts/looks up telegram_user_id in users and returns the internal users.id."""
        self.client.table("users").upsert(
            {"telegram_user_id": telegram_user_id},
            on_conflict="telegram_user_id"
        ).execute()

        res = (
            self.client.table("users")
            .select("id")
            .eq("telegram_user_id", telegram_user_id)
            .execute()
        )
        if not res.data:
            raise RuntimeError(f"Failed to retrieve users.id for telegram_user_id={telegram_user_id}")
        return res.data[0]["id"]

    def _get_telegram_id_for_user_pk(self, user_pk: Optional[int]) -> Optional[int]:
        """Resolves an internal users.id primary key back to its telegram_user_id."""
        if user_pk is None:
            return None
        res = (
            self.client.table("users")
            .select("telegram_user_id")
            .eq("id", user_pk)
            .execute()
        )
        if res.data:
            return res.data[0]["telegram_user_id"]
        return user_pk

    def _format_company_record(self, row: Dict[str, Any], owner_tg_id: Optional[int] = None) -> Dict[str, Any]:
        """Normalizes a Supabase companies row to the required Python dictionary format."""
        resolved_owner = (
            owner_tg_id
            if owner_tg_id is not None
            else self._get_telegram_id_for_user_pk(row.get("owner_id"))
        )
        return {
            "company_id": row["id"],
            "company_name": row["name"],
            "invite_code": row.get("invite_code", ""),
            "passcode_hash": row.get("passcode_hash", ""),
            "owner": resolved_owner,
            "members": row.get("members") or [],
        }

    def create_company(
        self, company_name: str, passcode_hash: str, owner_id: int, invite_code: str
    ) -> Dict[str, Any]:
        """Ensures user exists, inserts into companies, and initializes Storage folder."""
        clean_name = company_name.strip()

        # Check if company with that name already exists
        existing = (
            self.client.table("companies")
            .select("id")
            .ilike("name", clean_name)
            .execute()
        )
        if existing.data:
            raise ValueError(f"Company '{clean_name}' already exists.")

        # 1. Ensure user row exists first in 'users' (telegram_user_id = owner_id) and get users.id
        db_user_id = self._ensure_user_exists(owner_id)

        # 2. Insert into companies
        payload = {
            "name": clean_name,
            "invite_code": invite_code.strip().upper(),
            "passcode_hash": passcode_hash,
            "owner_id": db_user_id,
            "members": [owner_id],
        }
        response = self.client.table("companies").insert(payload).execute()
        if not response.data:
            raise RuntimeError("Failed to insert company record into Supabase.")

        created_row = response.data[0]
        company_id = created_row["id"]

        # 3. Upload b"" to f"{company_id}/.keep" in Storage so the folder is visible immediately
        try:
            self.client.storage.from_(self.STORAGE_BUCKET).upload(
                path=f"{company_id}/.keep",
                file=b"",
                file_options={"content-type": "text/plain", "upsert": "true"},
            )
        except Exception as err:
            print(f"Notice: Could not create storage .keep file for company {company_id}: {err}")

        return self._format_company_record(created_row, owner_tg_id=owner_id)

    def get_company_by_invite(self, invite_code: str) -> Optional[Dict[str, Any]]:
        """Queries companies by case-insensitive invite_code."""
        response = (
            self.client.table("companies")
            .select("*")
            .ilike("invite_code", invite_code.strip())
            .execute()
        )
        if not response.data:
            return None
        return self._format_company_record(response.data[0])

    def add_company_member(self, company_id: int, user_id: int) -> None:
        """Ensures user_id exists in users, then appends user_id to companies.members."""
        # Ensure user row exists in users table first
        self._ensure_user_exists(user_id)

        response = (
            self.client.table("companies")
            .select("members")
            .eq("id", company_id)
            .execute()
        )
        if not response.data:
            raise ValueError(f"Company with ID {company_id} not found.")

        members: List[int] = response.data[0].get("members") or []
        if user_id not in members:
            members.append(user_id)
            self.client.table("companies").update({"members": members}).eq("id", company_id).execute()

    def list_user_companies(self, user_id: int) -> List[Dict[str, Any]]:
        """Lists companies where user_id is owner or a member."""
        response = self.client.table("companies").select("*").order("id", desc=False).execute()
        db_user_res = (
            self.client.table("users")
            .select("id")
            .eq("telegram_user_id", user_id)
            .execute()
        )
        db_user_pk = db_user_res.data[0]["id"] if db_user_res.data else None

        joined: List[Dict[str, Any]] = []
        for row in (response.data or []):
            members = row.get("members") or []
            is_owner = db_user_pk is not None and row.get("owner_id") == db_user_pk
            if is_owner or user_id in members:
                joined.append(
                    self._format_company_record(
                        row,
                        owner_tg_id=user_id if is_owner else None,
                    )
                )
        return joined

# -----------------------------------------------------------------
# Functions to handle resume uploading, listing, deleting in supabase
# -----------------------------------------------------------------
    def parse_pdf_bytes(self, file_name: str, pdf_bytes: bytes):
        """Parses raw PDF bytes using ResumePDFParser."""
        from data_manager_modules.data_manager_resume_parser import ResumePDFParser
        return ResumePDFParser.parse_pdf_bytes(file_name, pdf_bytes)

    def upload_resume_bytes(
        self, file_name: str, pdf_bytes: bytes, company_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Parses bytes, uploads to Storage bucket 'resume_files', and saves into resume_files table."""
        clean_name = re.sub(r"\s+", "_", os.path.basename(str(file_name or "")).strip()) or "resume.pdf"

        # 1. Parse pdf_bytes with self.parse_pdf_bytes
        resume_obj = self.parse_pdf_bytes(clean_name, pdf_bytes)

        # 2. Upload to Storage ('resume_files' bucket) at path f"{company_id}/{clean_name}"
        storage_path = f"{company_id}/{clean_name}" if company_id is not None else clean_name
        self.client.storage.from_(self.STORAGE_BUCKET).upload(
            path=storage_path,
            file=pdf_bytes,
            file_options={"content-type": "application/pdf", "upsert": "true"},
        )
        pdf_url = self.client.storage.from_(self.STORAGE_BUCKET).get_public_url(storage_path)

        # 3. Update existing row or insert new row in resume_files table
        record = {
            "company_id": company_id,
            "file_name": clean_name,
            "pdf_url": pdf_url,
            "parsed_text": resume_obj.raw_text,
            "pages": resume_obj.pages,
            "status": resume_obj.status,
            "invalid_reason": resume_obj.reason,
        }
        existing_query = (
            self.client.table("resume_files")
            .select("id")
            .eq("file_name", clean_name)
        )
        if company_id is not None:
            existing_query = existing_query.eq("company_id", company_id)
        else:
            existing_query = existing_query.is_("company_id", "null")
        existing = existing_query.execute()
        if existing.data:
            self.client.table("resume_files").update(record).eq("id", existing.data[0]["id"]).execute()
        else:
            self.client.table("resume_files").insert(record).execute()

        # 4. Return normalized dictionary
        return {
            "file": clean_name,
            "file_name": clean_name,
            "status": resume_obj.status,
            "reason": resume_obj.reason,
            "pages": resume_obj.pages,
            "text": resume_obj.raw_text,
            "pdf_url": pdf_url,
            "company_id": company_id,
            "source": "Supabase Cloud",
        }

    def fetch_resume_files(self, company_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Retrieves file metadata records from the resume_files table, strictly scoped by company_id."""
        print("Fetching file list from Supabase 'resume_files' table...")
        query = self.client.table("resume_files").select(
            "id, company_id, file_name, pdf_url, parsed_text, pages, status, invalid_reason"
        )
        if company_id is not None:
            query = query.eq("company_id", company_id)
        else:
            # Multi-tenant isolation: Never leak other companies' resumes when company_id is omitted
            query = query.is_("company_id", "null")
        response = query.execute()
        return response.data or []

    def list_company_resumes(self, company_id: int) -> List[Dict[str, Any]]:
        """Queries resume_files where company_id == company_id."""
        response = (
            self.client.table("resume_files")
            .select("id, company_id, file_name, pdf_url, parsed_text, pages, status, invalid_reason")
            .eq("company_id", company_id)
            .order("id", desc=False)
            .execute()
        )
        rows = response.data or []
        return [
            {
                "id": row["id"],
                "file": row["file_name"],
                "file_name": row["file_name"],
                "status": row.get("status", "valid"),
                "reason": row.get("invalid_reason") or "",
                "pages": row.get("pages") or 0,
                "text": row.get("parsed_text") or "",
                "pdf_url": row.get("pdf_url") or "",
                "source": "Supabase Cloud",
            }
            for row in rows
        ]

    def download_resume_bytes(self, company_id: int, file_name: str) -> Optional[bytes]:
        """Downloads raw PDF bytes from Supabase Storage path f'{company_id}/{file_name}'."""
        storage_path = f"{company_id}/{file_name}"
        try:
            data = self.client.storage.from_(self.STORAGE_BUCKET).download(storage_path)
            return data if data else None
        except Exception as err:
            print(f"Notice: Could not download '{storage_path}' from Storage: {err}")
            return None

    def delete_company_resume(self, company_id: int, file_name: str) -> bool:
        """Deletes the file from Storage and its row in resume_files."""
        existing = (
            self.client.table("resume_files")
            .select("id")
            .eq("company_id", company_id)
            .eq("file_name", file_name)
            .execute()
        )
        if not existing.data:
            return False

        # Delete from Storage bucket
        storage_path = f"{company_id}/{file_name}"
        try:
            self.client.storage.from_(self.STORAGE_BUCKET).remove([storage_path])
        except Exception as err:
            print(f"Notice: Storage deletion failed for '{storage_path}': {err}")

        # Delete row from resume_files table
        (
            self.client.table("resume_files")
            .delete()
            .eq("company_id", company_id)
            .eq("file_name", file_name)
            .execute()
        )
        return True

    def clear_company_resumes(self, company_id: int) -> None:
        """Deletes all resumes for company_id from Storage and resume_files."""
        rows = (
            self.client.table("resume_files")
            .select("file_name")
            .eq("company_id", company_id)
            .execute()
        ).data or []

        if rows:
            storage_paths = [f"{company_id}/{r['file_name']}" for r in rows]
            try:
                self.client.storage.from_(self.STORAGE_BUCKET).remove(storage_paths)
            except Exception as err:
                print(f"Notice: Bulk Storage deletion failed for company {company_id}: {err}")

        self.client.table("resume_files").delete().eq("company_id", company_id).execute()

# -----------------------------------------------------------------
# Functions to handle business rules uploading to supabase
# -----------------------------------------------------------------

    PRIORITY_WEIGHTS: Dict[str, int] = {
        "must": 4,
        "important": 3,
        "nice": 2,
        "can consider": 1,
        "reject": 0,
    }

    def _validate_and_normalize_rules(
        self, rules: Optional[List[Dict[str, Any]]], strict: bool = True
    ) -> List[Dict[str, Any]]:
        """Validates on write (strict=True) and normalizes on read (strict=False)."""
        if not rules:
            return []
        if not isinstance(rules, list):
            if strict:
                raise ValueError("Rules must be provided as a list of rule dictionaries.")
            return []

        normalized: List[Dict[str, Any]] = []
        for idx, rule in enumerate(rules):
            if not isinstance(rule, dict):
                if strict:
                    raise ValueError(f"Rule at index {idx} must be a dictionary.")
                continue

            text = str(rule.get("text", "")).strip()
            if not text:
                if strict:
                    raise ValueError(f"Rule at index {idx} is missing non-empty 'text'.")
                continue

            raw_prio = str(rule.get("priority", "")).strip().lower()
            if raw_prio not in self.PRIORITY_WEIGHTS:
                if strict:
                    raise ValueError(
                        f"Invalid priority '{raw_prio}' on rule '{text}'. "
                        f"Allowed: {list(self.PRIORITY_WEIGHTS.keys())}"
                    )
                raw_prio = "reject"

            expected_weight = self.PRIORITY_WEIGHTS[raw_prio]
            if "weight" in rule and rule["weight"] is not None:
                try:
                    provided_weight = int(rule["weight"])
                except (ValueError, TypeError):
                    if strict:
                        raise ValueError(f"Weight for rule '{text}' must be an integer.")
                    provided_weight = expected_weight

                if strict and provided_weight != expected_weight:
                    raise ValueError(
                        f"Weight mismatch for priority '{raw_prio}': expected {expected_weight}, got {provided_weight}."
                    )

            normalized.append({
                "text": text,
                "priority": raw_prio,
                "weight": expected_weight,
            })

        return normalized

    def _format_rule_set_record(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """Normalizes a Supabase business_rules row to the required dictionary format."""
        return {
            "rule_set_id": row["id"],
            "company_id": row["company_id"],
            "set_name": row.get("set_name", ""),
            "rules": self._validate_and_normalize_rules(row.get("rules"), strict=False),
        }

    def list_company_rule_sets(self, company_id: int) -> List[Dict[str, Any]]:
        """Fetches all rows from business_rules where company_id == company_id (ordered by id asc)."""
        response = (
            self.client.table("business_rules")
            .select("id, company_id, set_name, rules, created_at")
            .eq("company_id", company_id)
            .order("id", desc=False)
            .execute()
        )
        rows = response.data or []
        return [self._format_rule_set_record(row) for row in rows]

    def create_company_rule_set(
        self,
        company_id: int,
        set_name: str,
        rules: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Creates a new Rule Set row in business_rules for company_id."""
        clean_name = (set_name or "").strip()
        if not clean_name:
            raise ValueError("Rule set 'set_name' cannot be empty.")

        # Case-insensitive uniqueness check within company_id
        existing = (
            self.client.table("business_rules")
            .select("id")
            .eq("company_id", company_id)
            .ilike("set_name", clean_name)
            .execute()
        )
        if existing.data:
            raise ValueError(f"Rule Set '{clean_name}' already exists for company_id={company_id}.")

        validated_rules = self._validate_and_normalize_rules(rules, strict=True)

        payload = {
            "company_id": company_id,
            "set_name": clean_name,
            "rules": validated_rules,
        }
        response = self.client.table("business_rules").insert(payload).execute()
        if not response.data:
            raise RuntimeError("Failed to insert rule set into Supabase.")

        return self._format_rule_set_record(response.data[0])

    def update_company_rule_set(
        self,
        company_id: int,
        rule_set_id: int,
        set_name: Optional[str] = None,
        rules: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Updates an existing business_rules row in place so business_rules.id is preserved."""
        # Verify row exists for this company_id
        current = (
            self.client.table("business_rules")
            .select("id, company_id, set_name, rules")
            .eq("id", rule_set_id)
            .eq("company_id", company_id)
            .execute()
        )
        if not current.data:
            raise ValueError(f"Rule Set id={rule_set_id} not found for company_id={company_id}.")

        update_payload: Dict[str, Any] = {}

        if set_name is not None:
            clean_name = set_name.strip()
            if not clean_name:
                raise ValueError("Rule set 'set_name' cannot be empty.")

            # Check uniqueness excluding the current rule_set_id
            dup = (
                self.client.table("business_rules")
                .select("id")
                .eq("company_id", company_id)
                .ilike("set_name", clean_name)
                .neq("id", rule_set_id)
                .execute()
            )
            if dup.data:
                raise ValueError(f"Another Rule Set named '{clean_name}' already exists for company_id={company_id}.")
            update_payload["set_name"] = clean_name

        if rules is not None:
            update_payload["rules"] = self._validate_and_normalize_rules(rules, strict=True)

        if not update_payload:
            return self._format_rule_set_record(current.data[0])

        response = (
            self.client.table("business_rules")
            .update(update_payload)
            .eq("id", rule_set_id)
            .eq("company_id", company_id)
            .execute()
        )
        if not response.data:
            raise RuntimeError(f"Failed to update Rule Set id={rule_set_id}.")

        return self._format_rule_set_record(response.data[0])

    def delete_company_rule_set(self, company_id: int, rule_set_id: int) -> bool:
        """Deletes the business_rules row and cleans up referencing results."""
        # Verify existence first
        existing = (
            self.client.table("business_rules")
            .select("id")
            .eq("id", rule_set_id)
            .eq("company_id", company_id)
            .execute()
        )
        if not existing.data:
            return False

        # Clean up any results referencing this business_rules_id
        self.client.table("results").delete().eq("business_rules_id", rule_set_id).execute()

        # Delete the business_rules row
        self.client.table("business_rules").delete().eq("id", rule_set_id).eq("company_id", company_id).execute()
        return True

# -------------------------------------------------------------------------
# Results & AI Summary persistence
# -------------------------------------------------------------------------

    def save_screening_results(
        self,
        company_id: int,
        ranked_candidates: List[Dict[str, Any]],
        summary_data: Optional[Dict[str, Any]],
        filtered_resumes: Optional[Dict[str, Any]] = None,
        business_rules_id: Optional[int] = None,
    ) -> None:
        """Persists screening results and optional AI summary to Supabase."""
        # 1. Resolve rule_row_id
        rule_row_id = business_rules_id
        if rule_row_id is None:
            rule_resp = (
                self.client.table("business_rules")
                .select("id")
                .eq("company_id", company_id)
                .order("id", desc=True)
                .limit(1)
                .execute()
            )
            if rule_resp.data:
                rule_row_id = rule_resp.data[0]["id"]

        # 2. Build the filtered_resume JSON payload
        fr = filtered_resumes or {}
        payload = {
            "accepted": fr.get("accepted", []),
            "rejected": fr.get("rejected", []),
            "invalid": fr.get("invalid", []),
            "ranked_candidates": ranked_candidates,
        }

        # 3. Insert into results and read back the inserted result_id
        res_insert = (
            self.client.table("results")
            .insert({
                "company_id": company_id,
                "business_rules_id": rule_row_id,
                "filtered_resume": payload,
            })
            .execute()
        )
        if not res_insert.data:
            raise RuntimeError("Failed to insert screening results into Supabase.")

        result_id = res_insert.data[0]["id"]

        # 4. If summary_data is provided, insert into summaries
        if summary_data is not None:
            self.client.table("summaries").insert({
                "result_id": result_id,
                "summary": summary_data,
            }).execute()

        # 5. Sync documents flagged invalid during screening back to resume_files
        for entry in fr.get("invalid", []):
            fname = entry.get("file") or entry.get("file_name")
            if not fname:
                continue
            reason = entry.get("reason") or "Marked invalid during screening"
            try:
                (
                    self.client.table("resume_files")
                    .update({"status": "invalid", "invalid_reason": reason})
                    .eq("company_id", company_id)
                    .eq("file_name", fname)
                    .execute()
                )
            except Exception as err:
                print(f"Notice: Could not sync invalid status for '{fname}': {err}")

    def get_screening_results(
        self,
        company_id: int,
        business_rules_id: Optional[int] = None,
    ) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """Fetches the latest screening results and linked AI summary."""
        # 1. Query results filtered by company_id (and optional business_rules_id)
        query = self.client.table("results").select("*").eq("company_id", company_id)
        if business_rules_id is not None:
            query = query.eq("business_rules_id", business_rules_id)

        res = query.order("created_at", desc=True).limit(1).execute()

        # 2. If none found, return ([], None)
        if not res.data:
            return [], None

        row = res.data[0]

        # 3. Extract ranked candidates from filtered_resume JSON
        fr = row.get("filtered_resume") or {}
        ranked = fr.get("ranked_candidates") or fr.get("accepted") or []

        # 4. Query summaries where result_id == row["id"]
        sum_res = (
            self.client.table("summaries")
            .select("summary")
            .eq("result_id", row["id"])
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        summary_data = sum_res.data[0].get("summary") if sum_res.data else None

        # 5. Return (ranked, summary_data)
        return ranked, summary_data
