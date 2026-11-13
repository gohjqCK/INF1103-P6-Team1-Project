# Handles the Supabase business_rules table
#
# Table layout: id | company_id | set | rules (text) | weightage (int) | created_at
# One row per rule. Rules with the same company_id + set number form one "set".
from typing import Any, Dict, List, Optional

from data_manager_modules.data_manager_supabase_handler import SupabaseHandler


class BusinessRulesHandler:
    # Reads, saves and deletes a company's business rule sets in Supabase

    TABLE = "business_rules"
    PRIORITY_TO_WEIGHT = {"must": 4, "important": 3, "nice": 2, "can consider": 1, "reject": 0}
    WEIGHT_TO_PRIORITY = {weight: priority for priority, weight in PRIORITY_TO_WEIGHT.items()}

    def __init__(self, db_handler: Optional[SupabaseHandler] = None):
        # Reuse an existing Supabase connection if one is passed in
        self._client = (db_handler or SupabaseHandler()).client

    # ---------------------- Sets ----------------------

    def get_rule_sets(self, company_id: int) -> List[int]:
        """Returns the company's set numbers with no repeats, e.g. rows 1,1,1,2,2,3 -> [1, 2, 3].
        An empty list means the company has no sets yet (prompt them to create one)."""
        response = (
            self._client.table(self.TABLE)
            .select("set")
            .eq("company_id", company_id)
            .execute()
        )
        return sorted({row["set"] for row in (response.data or []) if row.get("set") is not None})

    def get_next_set_number(self, company_id: int) -> int:
        """Returns the number to use when creating a new set (highest existing set + 1)."""
        sets = self.get_rule_sets(company_id)
        return (max(sets) + 1) if sets else 1

    # ---------------------- Rules ----------------------

    def get_business_rules(self, company_id: int, set_id: int) -> List[Dict[str, Any]]:
        """Returns the rules in one set, in the app's format:
        [{"id": 12, "text": "python", "priority": "must"}, ...]
        "id" is the database row id, used to delete a single rule."""
        response = (
            self._client.table(self.TABLE)
            .select("id, rules, weightage")
            .eq("company_id", company_id)
            .eq("set", set_id)
            .order("id")
            .execute()
        )
        return [
            {
                "id": row["id"],
                "text": row["rules"],
                "priority": self.WEIGHT_TO_PRIORITY.get(row.get("weightage"), "reject"),
            }
            for row in (response.data or [])
        ]

    def upload_business_rules(
        self,
        company_id: int,
        set_id: int,
        rules: List[Dict[str, Any]],
        replace: bool = True,
    ) -> List[Dict[str, Any]]:
        """Saves rules ({"text", "priority"}) into a company's set.
        replace=True  : the set will contain exactly these rules (old ones removed).
        replace=False : these rules are added to the set's existing rules.
        Returns the inserted database rows."""
        records = [self._to_record(company_id, set_id, rule) for rule in rules]

        if replace:
            self.delete_rule_set(company_id, set_id)
        if not records:
            return []

        response = self._client.table(self.TABLE).insert(records).execute()
        return response.data or []

    def delete_business_rule(self, company_id: int, set_id: int, rule_id: int) -> bool:
        """Deletes one rule (by its row id) from a company's set. Returns True if a row was deleted."""
        response = (
            self._client.table(self.TABLE)
            .delete()
            .eq("company_id", company_id)
            .eq("set", set_id)
            .eq("id", rule_id)
            .execute()
        )
        return bool(response.data)

    def delete_rule_set(self, company_id: int, set_id: int) -> int:
        """Deletes every rule in a company's set. Returns how many rows were deleted."""
        response = (
            self._client.table(self.TABLE)
            .delete()
            .eq("company_id", company_id)
            .eq("set", set_id)
            .execute()
        )
        return len(response.data or [])

    # ---------------------- Helpers ----------------------

    def _to_record(self, company_id: int, set_id: int, rule: Dict[str, Any]) -> Dict[str, Any]:
        """Converts an app rule {"text", "priority"} into a business_rules table row."""
        text = str(rule.get("text", "")).strip()
        priority = str(rule.get("priority", "reject")).strip().lower()
        if not text:
            raise ValueError("Every rule needs text.")
        if priority not in self.PRIORITY_TO_WEIGHT:
            raise ValueError(
                f"Invalid priority '{priority}' for rule '{text}'. "
                f"Use one of: {', '.join(self.PRIORITY_TO_WEIGHT)}"
            )
        return {
            "company_id": company_id,
            "set": set_id,
            "rules": text,
            "weightage": self.PRIORITY_TO_WEIGHT[priority],
        }
