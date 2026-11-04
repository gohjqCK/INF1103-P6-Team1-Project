"""Concrete CLI implementation of BaseIOManager for terminal users."""
import sys
from typing import Any, Dict, List, Optional

from io_manager_modules.io_manager_base import BaseIOManager
from io_manager_modules.io_manager_input_validator import InputValidator
from io_manager_modules.io_manager_result_presenter import ResultPresenter
from io_manager_modules.io_manager_rule_handler import RuleInputHandler

try:
    from data_manager_modules.data_manager_side import DataManager
    _HAS_OOP_DATA_MANAGER = True
except Exception:
    _HAS_OOP_DATA_MANAGER = False
    try:
        import Data_Manager
    except Exception:
        Data_Manager = None

class CLIIOManager(BaseIOManager):
    """Coordinates terminal dashboard, user menus, and delegates to helper classes.

    Demonstrates Composition (owns InputValidator, ResultPresenter, RuleInputHandler)
    and Inheritance/Polymorphism (implements BaseIOManager).
    """

    def __init__(
        self,
        validator: Optional[InputValidator] = None,
        presenter: Optional[ResultPresenter] = None,
        rule_handler: Optional[RuleInputHandler] = None,
    ):
        self._validator = validator or InputValidator()
        self._presenter = presenter or ResultPresenter(self._validator)
        self._rule_handler = rule_handler or RuleInputHandler(self._validator)

    # -------------------------------------------------------------------------
    # BaseIOManager Contract Implementations
    # -------------------------------------------------------------------------

    def display_message(self, message: str) -> None:
        print(message)

    def display_error(self, error_message: str) -> None:
        print(f"\n  [!] ERROR: {error_message}\n")

    def display_success(self, success_message: str) -> None:
        print(f"  [+] SUCCESS: {success_message}")

    def display_screening_results(
        self, ranked_candidates: List[Any], top_n: Optional[int] = None
    ) -> List[Any]:
        return self._presenter.display_screening_results(ranked_candidates, top_n)

    # -------------------------------------------------------------------------
    # Rule and Results Helper Pass-Throughs
    # -------------------------------------------------------------------------

    def view_saved_results(
        self, file_path: Optional[str] = None, top_n: Optional[int] = None, output_dir: str = "output"
    ) -> None:
        self._presenter.view_saved_results(file_path=file_path, top_n=top_n, output_dir=output_dir)

    
    def _fetch_rules_from_storage(self) -> List[Dict[str, Any]]:
        if _HAS_OOP_DATA_MANAGER:
            try:
                return DataManager.get_businessrules()
            except Exception:
                pass
        try:
            with open("Business_Rules.json", "r", encoding="utf-8") as f:
                import json
                return json.load(f)
        except Exception:
            return []

    def _persist_rules_to_storage(self, rules: List[Dict[str, Any]]) -> None:
        """Saves rules to DataManager or falls back to local Business_Rules.json."""
        if _HAS_OOP_DATA_MANAGER:
            try:
                DataManager.save_businessrules(rules)
                return
            except Exception:
                pass
        try:
            import json
            with open("Business_Rules.json", "w", encoding="utf-8") as f:
                json.dump(rules, f, indent=4)
        except Exception:
            pass
    
    # -------------------------------------------------------------------------
    # Interactive Main Dashboard Loop
    # -------------------------------------------------------------------------

    def get_employer_inputs(self, rerun_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Main terminal menu dashboard enforcing prerequisite guards before pipeline handoff."""
        rules = self._fetch_rules_from_storage()
        config = rerun_config if rerun_config else {
            "business_rules": rules,
            "pdf_directory": "resumes",
            "top_n": 3,
            "output_directory": "output",
        }
        if "output_directory" not in config:
            config["output_directory"] = "output"

        while True:
            rules_status = (
                f"{len(config['business_rules'])} Rule(s) Configured"
                if config["business_rules"]
                else "NOT SET (Required)"
            )

            print("\n=============================================")
            print("          RESUME SCREENER SETUP MENU         ")
            print("=============================================")
            print(f"1. Manage Business Rules Criteria  [{rules_status}]")
            print(f"2. Configure Resumes & Limit       [Folder: '{config['pdf_directory']}', Limit: {config['top_n']}]")
            print(f"3. Configure Output Results Folder [Folder: '{config['output_directory']}']")
            print("4. Proceed to Resume Screening")
            print("5. View Screening Results (from JSON)")
            print("6. Exit Application")
            print("=============================================")

            choice = self._validator.get_valid_menu_choice(["1", "2", "3", "4", "5", "6"])

            if choice == "1":
                config["business_rules"] = self._rule_handler.manage_business_rules(config["business_rules"])
                self._persist_rules_to_storage(config["business_rules"])

            elif choice == "2":
                folder, limit = self._validator.configure_resumes_and_limit()
                config["pdf_directory"] = folder
                config["top_n"] = limit

            elif choice == "3":
                config["output_directory"] = self._validator.get_valid_output_directory(config["output_directory"])

            elif choice == "4":
                if not config["business_rules"]:
                    self.display_error("You must configure at least one Business Rule (Option 1) before starting!")
                    continue

                is_valid, pdf_count, err_msg = self._validator.scan_pdf_count(config["pdf_directory"])
                if not is_valid:
                    self.display_error(f"{err_msg} Update folder via Option 2.")
                    continue
                if pdf_count == 0:
                    self.display_error(f"No PDFs found in '{config['pdf_directory']}'. Update via Option 2.")
                    continue

                if config["top_n"] > pdf_count:
                    self.display_message(f"  [*] Notice: Capping candidate limit from {config['top_n']} to available ({pdf_count}).")
                    config["top_n"] = pdf_count

                self.display_success("Configuration verified! Handing off to main pipeline...\n")
                return config

            elif choice == "5":
                self.view_saved_results(file_path=None, top_n=config["top_n"], output_dir=config["output_directory"])

            elif choice == "6":
                self.display_message("\nExiting Resume Screener. Goodbye!")
                sys.exit(0)