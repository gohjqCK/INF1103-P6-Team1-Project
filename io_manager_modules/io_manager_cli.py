"""Concrete CLI implementation of BaseIOManager for terminal users."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
from typing import Any, Dict, List, Optional, Tuple

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
    """Coordinates terminal dashboard, user menus, company profiles, and delegates to helper classes.

    Demonstrates Composition (owns InputValidator, ResultPresenter, RuleInputHandler, DataManager)
    and Inheritance/Polymorphism (implements BaseIOManager).
    """

    def __init__(
        self,
        validator: Optional[InputValidator] = None,
        presenter: Optional[ResultPresenter] = None,
        rule_handler: Optional[RuleInputHandler] = None,
        data_manager: Optional[Any] = None,
        data_file: str = "companies.json",
    ):
        self._validator = validator or InputValidator()
        self._presenter = presenter or ResultPresenter(self._validator)
        self._rule_handler = rule_handler or RuleInputHandler(self._validator)

        if data_manager is not None:
            self._data_manager = data_manager
        elif _HAS_OOP_DATA_MANAGER:
            self._data_manager = DataManager()
        else:
            self._data_manager = None

        self._use_cloud = bool(getattr(self._data_manager, "CLOUD_READY", False))
        self._next_stub_company_id = 101
        self._companies: Dict[str, Dict[str, Any]] = {}
        self._active_company_name: Optional[str] = None
        self._active_company_id: Optional[int] = None

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

    def view_summary_report(self, summary_file: str = "summary.json") -> None:
        self._presenter.display_summary_report(summary_file=summary_file)

    def _fetch_rules_from_storage(self) -> List[Dict[str, Any]]:
        if self._data_manager and hasattr(self._data_manager, "get_businessrules"):
            try:
                return self._data_manager.get_businessrules()
            except Exception:
                pass
        try:
            with open("Business_Rules.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _persist_rules_to_storage(self, rules: List[Dict[str, Any]]) -> None:
        """Saves rules to DataManager or falls back to local Business_Rules.json."""
        if self._data_manager and hasattr(self._data_manager, "save_businessrules"):
            try:
                self._data_manager.save_businessrules(rules)
                return
            except Exception:
                pass
        try:
            with open("Business_Rules.json", "w", encoding="utf-8") as f:
                json.dump(rules, f, indent=4)
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # Company Folder & Cloud Management (Mirrors Telegram Authentication)
    # -------------------------------------------------------------------------

    def _load_companies(self) -> Dict[str, Dict[str, Any]]:
        """Loads companies from in-memory stub (no local companies.json file writes)."""
        return self._companies

    def _save_companies(self) -> None:
        """No-op stub; companies are stored in memory or synced via DataManager cloud methods."""
        pass

    def _next_company_id(self) -> int:
        existing = [
            int(info["company_id"])
            for info in self._companies.values()
            if isinstance(info, dict) and isinstance(info.get("company_id"), int)
        ]
        if existing:
            return max(existing) + 1
        cid = self._next_stub_company_id
        self._next_stub_company_id += 1
        return cid

    def authenticate_company(self) -> Tuple[str, int]:
        """Prompts employer to select, create, or join a company folder."""
        while True:
            print("\n=============================================")
            print("        COMPANY FOLDER AUTHENTICATION        ")
            print("=============================================")
            options = []
            if self._companies:
                print("1. Select an Existing Company Folder")
                options.append("1")
            print("2. Create New Company Folder")
            options.append("2")
            print("3. Join Company with Invite Code")
            options.append("3")
            print("=============================================")

            choice = self._validator.get_valid_menu_choice(options)

            if choice == "1":
                comp_names = list(self._companies.keys())
                print("\nAvailable Companies:")
                for idx, cname in enumerate(comp_names, 1):
                    cid = self._companies[cname].get("company_id", "N/A")
                    print(f"  {idx}. {cname} (ID: #{cid})")
                print("  0. Back to Selection")

                valid_nums = [str(i) for i in range(len(comp_names) + 1)]
                sel = self._validator.get_valid_menu_choice(valid_nums)
                if sel == "0":
                    continue

                chosen_name = comp_names[int(sel) - 1]
                stored_hash = self._companies[chosen_name].get("passcode_hash")

                if stored_hash:
                    passcode = self._validator.safe_input(f"Enter passcode for '{chosen_name}': ").strip()
                    if hashlib.sha256(passcode.encode("utf-8")).hexdigest() != stored_hash:
                        self.display_error("Incorrect passcode.")
                        continue

                self._active_company_name = chosen_name
                self._active_company_id = self._companies[chosen_name].get("company_id", 101)
                inv = self._companies[chosen_name].get("invite_code", "N/A")
                self.display_success(f"Authenticated as '{self._active_company_name}' (ID: #{self._active_company_id})")
                print(f"  🔑 Team Invite Code: {inv}")
                return self._active_company_name, self._active_company_id

            elif choice == "2":
                name = self._validator.safe_input("Enter new Company Name: ").strip()
                if len(name) < 2:
                    self.display_error("Company name must be at least 2 characters.")
                    continue
                if name in self._companies:
                    self.display_error(f"Company '{name}' already exists. Please select it or choose another name.")
                    continue

                passcode = self._validator.safe_input(f"Set a passcode for '{name}' (min 4 characters): ").strip()
                if len(passcode) < 4:
                    self.display_error("Passcode must be at least 4 characters.")
                    continue

                prefix = "".join(c for c in name.upper() if c.isalnum())[:4] or "COMP"
                invite_code = f"{prefix}-{secrets.randbelow(9000) + 1000}"
                passcode_hash = hashlib.sha256(passcode.encode("utf-8")).hexdigest()

                if (
                    self._use_cloud
                    and self._data_manager is not None
                    and hasattr(self._data_manager, "create_company")
                ):
                    record = self._data_manager.create_company(
                        company_name=name,
                        passcode_hash=passcode_hash,
                        owner_id=0,
                        invite_code=invite_code,
                    )
                    cid = record["company_id"]
                    self._companies[name] = record
                else:
                    cid = self._next_company_id()
                    self._companies[name] = {
                        "company_id": cid,
                        "company_name": name,
                        "invite_code": invite_code,
                        "passcode_hash": passcode_hash,
                        "members": ["cli_admin"],
                    }

                self._active_company_name = name
                self._active_company_id = cid

                print("\n" + "=" * 55)
                print("         COMPANY CREATED SUCCESSFULLY!        ")
                print("=" * 55)
                print(f"  🏢 Company Name    : {name}")
                print(f"  🆔 Company ID      : #{cid}")
                print(f"  🔑 Team Invite Code: {invite_code}")
                print("=" * 55)
                print("  💡 IMPORTANT: Share this Invite Code with team members")
                print("     so they can join this company folder on Telegram!")
                print("=" * 55)
                self._validator.safe_input("\nPress [Enter] to continue to the main dashboard...")
                return self._active_company_name, self._active_company_id

            elif choice == "3":
                code = self._validator.safe_input("Enter Team Invite Code: ").strip().upper()
                target_record = None
                if (
                    self._use_cloud
                    and self._data_manager is not None
                    and hasattr(self._data_manager, "get_company_by_invite")
                ):
                    target_record = self._data_manager.get_company_by_invite(code)
                    if target_record:
                        self._companies[target_record["company_name"]] = target_record

                target_name = target_record["company_name"] if target_record else next(
                    (n for n, i in self._companies.items() if i.get("invite_code", "").upper() == code),
                    None,
                )
                if not target_name:
                    self.display_error("Invalid invite code. Please check and try again.")
                    continue

                passcode = self._validator.safe_input(f"Enter passcode for '{target_name}': ").strip()
                stored_hash = self._companies[target_name].get("passcode_hash")
                if hashlib.sha256(passcode.encode("utf-8")).hexdigest() != stored_hash:
                    self.display_error("Incorrect passcode.")
                    continue

                self._active_company_name = target_name
                self._active_company_id = self._companies[target_name].get("company_id", 101)
                inv = self._companies[target_name].get("invite_code", "N/A")
                self.display_success(f"Joined '{target_name}' (ID: #{self._active_company_id})!")
                print(f"  🔑 Team Invite Code: {inv}")
                return self._active_company_name, self._active_company_id

    def _get_cloud_resume_count(self) -> int:
        """Fetches count of resumes currently in Supabase for this company."""
        if not self._data_manager or not hasattr(self._data_manager, "db_handler"):
            return 0
        try:
            records = self._data_manager.db_handler.fetch_resume_files(company_id=self._active_company_id)
            return len(records)
        except Exception:
            return 0

    def configure_company_resumes(self, current_limit: int, current_dir: str) -> Tuple[str, int]:
        """Sub-menu allowing employer to use Cloud resumes or upload local PDFs to Cloud."""
        while True:
            cloud_count = self._get_cloud_resume_count()
            print("\n---------------------------------------------")
            print("       CONFIGURE RESUMES & TOP N LIMIT       ")
            print("---------------------------------------------")
            print(f"🏢 Active Company : {self._active_company_name} (ID: #{self._active_company_id})")
            print(f"☁️ Cloud Resumes  : {cloud_count} PDF(s) in Supabase")
            print(f"🎯 Current Limit  : Top {current_limit}")
            print(f"📁 Local Directory: '{current_dir}'")
            print("---------------------------------------------")
            print("1. Use Resumes from Supabase Cloud (uploaded via Telegram or CLI)")
            print("2. Upload Local PDF Folder to Supabase Cloud for this Company")
            print("3. Update Candidate Shortlist Limit (Top N) only")
            print("4. Return to Main Menu")
            print("---------------------------------------------")

            sub_choice = self._validator.get_valid_menu_choice(["1", "2", "3", "4"])

            if sub_choice == "1":
                if cloud_count == 0:
                    self.display_error("No resumes currently in Supabase Cloud. Upload via Telegram or Option 2 first!")
                    continue
                new_limit = self._validator.get_valid_top_n_candidates(max_available=cloud_count)
                self.display_success(f"Configured to screen {cloud_count} Cloud Resume(s) with Top {new_limit} limit.")
                return current_dir, new_limit

            elif sub_choice == "2":
                folder = self._validator.get_valid_pdf_directory()
                _, pdf_count, _ = self._validator.scan_pdf_count(folder)
                confirm = self._validator.safe_input(
                    f"Upload {pdf_count} PDF resume(s) from '{folder}' to Supabase Cloud for {self._active_company_name}? (y/n): "
                ).strip().lower()

                if confirm in ("y", "yes"):
                    print(f"\n  [+] Uploading {pdf_count} PDF(s) to Supabase Storage & Database...")
                    if self._data_manager and hasattr(self._data_manager, "upload_local_folder"):
                        uploaded = self._data_manager.upload_local_folder(folder, company_id=self._active_company_id)
                        self.display_success(f"Successfully processed and uploaded {len(uploaded)} resume(s) to Cloud!")
                    else:
                        self.display_error("DataManager upload handler not available.")

                    new_count = self._get_cloud_resume_count()
                    new_limit = self._validator.get_valid_top_n_candidates(max_available=new_count or pdf_count)
                    return folder, new_limit
                else:
                    print("Upload cancelled.")

            elif sub_choice == "3":
                max_avail = max(cloud_count, 1)
                new_limit = self._validator.get_valid_top_n_candidates(max_available=max_avail)
                self.display_success(f"Candidate limit updated to Top {new_limit}.")
                return current_dir, new_limit

            elif sub_choice == "4":
                return current_dir, current_limit

    # -------------------------------------------------------------------------
    # Interactive Main Dashboard Loop
    # -------------------------------------------------------------------------

    def get_employer_inputs(self, rerun_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Main terminal menu dashboard enforcing prerequisite guards before pipeline handoff."""
        if not self._active_company_name:
            self.authenticate_company()

        rules = self._fetch_rules_from_storage()
        config = rerun_config if rerun_config else {
            "company_name": self._active_company_name,
            "company_id": self._active_company_id,
            "business_rules": rules,
            "pdf_directory": "resumes",
            "top_n": 3,
            "output_directory": "output",
        }
        config["company_name"] = self._active_company_name
        config["company_id"] = self._active_company_id
        if "output_directory" not in config:
            config["output_directory"] = "output"

        while True:
            cloud_count = self._get_cloud_resume_count()
            rules_status = (
                f"{len(config['business_rules'])} Rule(s) Configured"
                if config["business_rules"]
                else "NOT SET (Required)"
            )
            cloud_status = f"{cloud_count} in Cloud" if cloud_count > 0 else "0 in Cloud"

            active_info = self._companies.get(self._active_company_name, {})
            active_invite = active_info.get("invite_code", "N/A")

            print("\n=============================================")
            print("                RESUM-AI SETUP MENU          ")
            print("=============================================")
            print(f"🏢 Company Folder  : {self._active_company_name} (ID: #{self._active_company_id})")
            print(f"🔑 Team Invite Code: {active_invite}")
            print("---------------------------------------------")
            print(f"1. Manage Business Rules Criteria  [{rules_status}]")
            print(f"2. Configure Resumes & Limit       [{cloud_status}, Limit: {config['top_n']}]")
            print(f"3. Configure Output Results Folder [Folder: '{config['output_directory']}']")
            print("4. Proceed to Resume Screening")
            print("5. View Screening Results (from JSON)")
            print("6. View AI Summary Report (summary.json)")
            print("7. Switch Active Company Folder")
            print("8. Exit Application")
            print("=============================================")

            choice = self._validator.get_valid_menu_choice(["1", "2", "3", "4", "5", "6", "7", "8"])

            if choice == "1":
                config["business_rules"] = self._rule_handler.manage_business_rules(config["business_rules"])
                self._persist_rules_to_storage(config["business_rules"])

            elif choice == "2":
                folder, limit = self.configure_company_resumes(config["top_n"], config["pdf_directory"])
                config["pdf_directory"] = folder
                config["top_n"] = limit

            elif choice == "3":
                config["output_directory"] = self._validator.get_valid_output_directory(config["output_directory"])

            elif choice == "4":
                if not config["business_rules"]:
                    self.display_error("You must configure at least one Business Rule (Option 1) before starting!")
                    continue

                cloud_count = self._get_cloud_resume_count()
                _, local_count, _ = self._validator.scan_pdf_count(config["pdf_directory"])

                if cloud_count == 0 and local_count == 0:
                    self.display_error(
                        "No resumes found in Supabase Cloud or in local directory. "
                        "Please upload resumes via Telegram or Option 2 first!"
                    )
                    continue

                total_avail = cloud_count if cloud_count > 0 else local_count
                if config["top_n"] > total_avail:
                    self.display_message(f"  [*] Notice: Capping candidate limit from {config['top_n']} to available ({total_avail}).")
                    config["top_n"] = total_avail

                config["company_name"] = self._active_company_name
                config["company_id"] = self._active_company_id

                self.display_success("Configuration verified! Handing off to main pipeline...\n")
                return config

            elif choice == "5":
                self.view_saved_results(file_path=None, top_n=config["top_n"], output_dir=config["output_directory"])

            elif choice == "6":
                self.view_summary_report("summary.json")

            elif choice == "7":
                self.authenticate_company()
                config["company_name"] = self._active_company_name
                config["company_id"] = self._active_company_id

            elif choice == "8":
                self.display_message("\nExiting RESUM-AI. Goodbye!")
                sys.exit(0)
