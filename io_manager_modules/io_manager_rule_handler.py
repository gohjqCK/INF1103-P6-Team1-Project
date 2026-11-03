"""Encapsulates business rules creation, deletion, deduplication, and display."""
from typing import Any, Dict, List, Optional

from io_manager_modules.io_manager_input_validator import InputValidator


class RuleInputHandler:
    """Manages business rules input, validation guards, and interactive sub-menu."""

    MIN_RULE_LENGTH = 5
    MAX_RULE_LENGTH = 300

    def __init__(self, validator: Optional[InputValidator] = None):
        self._validator = validator or InputValidator()

    def display_current_rules(self, rules: List[Dict[str, Any]]) -> None:
        """Prints all configured rules in an indexed list."""
        if not rules:
            print("\n  [i] No business rules currently configured.")
            return

        print("\n---------------- CURRENT BUSINESS RULES ----------------")
        for idx, rule in enumerate(rules, start=1):
            priority = rule.get("priority", "reject").upper()
            text = rule.get("text", "<unspecified>")
            print(f"  {idx}. [{priority}] {text}")
        print("-------------------------------------------------------")

    def add_business_rules(self, rules: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Captures rules line-by-line with length checks and duplicate guards."""
        print("\n--- ADD BUSINESS RULES ---")
        print("Enter requirements one at a time.")

        while True:
            rule_num = len(rules) + 1
            print(f"\n[Rule #{rule_num}]")

            while True:
                text = self._validator.safe_input("Enter rule requirement: ").strip()

                # Guard 1: Minimum content validation
                if len(text) < self.MIN_RULE_LENGTH:
                    print(f"\n  [!] ERROR: Rule text too short. Enter at least {self.MIN_RULE_LENGTH} characters.\n")
                    continue

                # Guard 2: Maximum boundary check
                if len(text) > self.MAX_RULE_LENGTH:
                    print(f"\n  [!] ERROR: Rule text too long (max {self.MAX_RULE_LENGTH} chars). Keep it concise.\n")
                    continue

                # Guard 3: Case-insensitive duplicate check
                is_duplicate = any(r.get("text", "").lower() == text.lower() for r in rules)
                if is_duplicate:
                    print(f"\n  [!] ERROR: Rule '{text}' is already in your list. Enter a unique rule.\n")
                    continue

                break

            priority = self._validator.get_valid_priority()
            rules.append({"text": text, "priority": priority})
            print(f"  [+] SUCCESS: Added Rule #{rule_num} [{priority}]: '{text}'")

            print("\nDo you want to add another rule?")
            more = self._validator.get_valid_menu_choice(["y", "n"])
            if more.lower() == "n":
                break

        return rules

    def delete_single_rule(self, rules: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Safely removes an existing rule by index."""
        if not rules:
            print("\n  [i] No rules available to delete.")
            return rules

        self.display_current_rules(rules)
        print("\nEnter rule number to remove (or '0' to cancel):")

        valid_choices = [str(i) for i in range(len(rules) + 1)]
        choice = self._validator.get_valid_menu_choice(valid_choices)

        if choice == "0":
            print("Deletion cancelled.")
            return rules

        try:
            removed_rule = rules.pop(int(choice) - 1)
            print(f"  [+] SUCCESS: Removed Rule: '{removed_rule.get('text', '')}'")
        except IndexError:
            print("\n  [!] ERROR: Selected rule index out of range.\n")

        return rules

    def manage_business_rules(self, existing_rules: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Sub-menu interface for viewing, adding, and clearing rules."""
        rules = list(existing_rules)

        while True:
            print("\n=============================================")
            print("          BUSINESS RULES MANAGEMENT          ")
            print("=============================================")
            print(f"Total Rules Configured: {len(rules)}")
            print("1. View Current Rules")
            print("2. Add New Rule(s)")
            print("3. Delete a Specific Rule")
            print("4. Clear All Rules")
            print("5. Save & Return to Main Menu")
            print("=============================================")

            sub_choice = self._validator.get_valid_menu_choice(["1", "2", "3", "4", "5"])

            if sub_choice == "1":
                self.display_current_rules(rules)
            elif sub_choice == "2":
                rules = self.add_business_rules(rules)
            elif sub_choice == "3":
                rules = self.delete_single_rule(rules)
            elif sub_choice == "4":
                if not rules:
                    print("\n  [i] Rules list is already empty.")
                    continue
                print("\nAre you sure you want to clear all rules?")
                if self._validator.get_valid_menu_choice(["y", "n"]) == "y":
                    rules.clear()
                    print("  [+] SUCCESS: All business rules cleared.")
            elif sub_choice == "5":
                return rules