import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

_IMPORT_ERRORS: Dict[str, Exception] = {}

# AI Manager
try:
    from ai_manager_modules.ai_manager import AIManager
    from ai_manager_modules.ai_manager_ollama_client import OllamaClient
except Exception as err:
    AIManager = None
    OllamaClient = None
    _IMPORT_ERRORS["AI Manager"] = err

# Data Manager (local-folder parser, used when the caller sends no resumes)
try:
    from data_manager_modules.ResumeFolderParser import ResumeFolderParser
except Exception as err:
    ResumeFolderParser = None
    _IMPORT_ERRORS["Data Manager (PDF parsing)"] = err

# Logic Manager
try:
    from Logic_manager_modules import Logic_Manager as LogicManager
    from Logic_manager_modules.OnlineResume import OnlineResume
    from Logic_manager_modules.OfflineResume import OfflineResume
except Exception as err:
    LogicManager = None
    OnlineResume = None
    OfflineResume = None
    _IMPORT_ERRORS["Logic Manager"] = err
try:
    from Logic_manager_modules.OverviewReport import LogicReportGenerator
except Exception as err:
    LogicReportGenerator = None
    _IMPORT_ERRORS["Overview Report"] = err
try:
    from Logic_manager_modules.SummaryBuilder import SummaryBuilder
except Exception as err:
    SummaryBuilder = None
    _IMPORT_ERRORS["Summary Builder"] = err

Notify = Callable[[str], None]


class MainProg:
    """Coordinates AI, Data and Logic managers. TelegramIOManager calls run()."""

    def __init__(self, output_dir: str = "output"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        for label, err in _IMPORT_ERRORS.items():
            print(f"  [!] {label} failed to import: {type(err).__name__}: {err}")

        self.ai_manager = None
        if AIManager is not None and OllamaClient is not None:
            try:
                self.ai_manager = AIManager(OllamaClient())
            except Exception as err:
                print(f"  [!] Could not create the AI Manager: {type(err).__name__}: {err}")

        self.report_generator = LogicReportGenerator(str(self.output_dir)) if LogicReportGenerator else None
        self.resume_parser = ResumeFolderParser() if ResumeFolderParser else None

    def check_ai_connection(self) -> bool:
        if self.ai_manager is None:
            return False
        try:
            return bool(self.ai_manager.check_connection())
        except Exception:
            return False

    # ------------------------------------------------------------------ pipeline
    def run(self, employer_inputs: Dict[str, Any],
            progress_callback: Optional[Notify] = None) -> Dict[str, Any]:
        """Returns {"ranked_candidates", "summary_data", "filtered_resumes"} (what the Telegram bot saves)."""
        notify: Notify = progress_callback or (lambda text: None)
        rules = [dict(rule) for rule in employer_inputs.get("business_rules", [])]
        top_n = employer_inputs.get("top_n") or 3

        # Stage 1: get the resumes (sent by the bot, else read from a local folder)
        resumes = self._load_resumes(employer_inputs)
        print(f"\n[Pipeline] Screening {len(resumes)} resume(s) against {len(rules)} rule(s)...")
        if not resumes:
            notify("No resumes could be read.")
            return self._package([], [], [], None)

        # Stage 2: screen (AI if Ollama is ready, otherwise offline fallback)
        results, ai_used = None, False
        if self.check_ai_connection():
            try:
                notify("AI online - generating rule keywords...")
                rules = self.ai_manager.add_keywords(rules)
                results = self._screen_with_ai(rules, resumes, notify)
                ai_used = True
            except Exception as err:
                print(f"  [!] AI screening failed ({type(err).__name__}: {err}) - using offline screening.")
                notify("AI failed - switching to offline screening...")
                rules = [dict(rule) for rule in employer_inputs.get("business_rules", [])]
        if results is None:
            notify("Using offline screening...")
            results = self._screen_offline(rules, resumes)

        # Stage 3: Logic Manager sorts results into accepted / rejected / invalid
        notify("Filtering and ranking candidates...")
        accepted, rejected, invalid = self._categorise(results, ai_used)
        accepted.sort(key=lambda c: c.get("score") or 0, reverse=True)

        # Stage 4: summary report - Logic Manager builds the statistics, AI writes the text
        summary_data = None
        if SummaryBuilder is not None:
            try:
                notify("Writing summary report...")
                model = self.ai_manager.model_name if ai_used else "offline keyword matching"
                summary_data = SummaryBuilder(rules, model, top_n).build(results)
                if ai_used:
                    summary_data["overall_summary"] = self.ai_manager.write_summary(summary_data)
                else:
                    summary_data["overall_summary"] = "AI was offline, so resumes were screened by keyword matching."
            except Exception as err:
                print(f"  [!] Could not create the summary: {err}")

        self._save_results(results)
        print(f"[Pipeline Complete] {len(accepted)} accepted, {len(rejected)} rejected, {len(invalid)} invalid.\n")
        return self._package(accepted, rejected, invalid, summary_data)

    # ------------------------------------------------------------------ stages
    def _load_resumes(self, employer_inputs: Dict[str, Any]) -> List[Dict[str, Any]]:
        sent = employer_inputs.get("resumes")
        if sent:
            return [dict(r) for r in sent]
        if self.resume_parser is None:
            return []
        return self.resume_parser.parse(employer_inputs.get("pdf_directory", "resumes"))

    def _screen_with_ai(self, rules, resumes, notify: Notify) -> List[Dict[str, Any]]:
        total, done, lock = len(resumes), [0], threading.Lock()

        def on_result(entry: Dict[str, Any]) -> None:
            with lock:
                done[0] += 1
                notify(f"AI screened {done[0]}/{total} resume(s)...")

        return self.ai_manager.screen_resumes(rules, resumes, on_result=on_result)

    @staticmethod
    def _screen_offline(rules, resumes) -> List[Dict[str, Any]]:
        if LogicManager is None:
            raise RuntimeError("Logic Manager is unavailable, so offline screening can't run.")
        valid = [r for r in resumes if r.get("status") == "valid"]
        invalid = [r for r in resumes if r.get("status") != "valid"]
        scored = LogicManager.offline_screening_func(valid, rules)
        for entry in invalid:
            entry["outcome"] = "invalid"
            entry["score"] = None
            entry.setdefault("reason", "")
        return scored + invalid

    @staticmethod
    def _categorise(results: List[Dict[str, Any]], ai_used: bool):
        """Uses Logic_Manager.filter_resume_func, then maps the result objects back to the full dicts."""
        if LogicManager is None:
            raise RuntimeError("Logic Manager is unavailable.")
        resume_type = OnlineResume if ai_used else OfflineResume
        acc_list, rej_list, inv_list = LogicManager.filter_resume_func(results, resume_type)

        label_by_file: Dict[str, str] = {}
        for label, lst in (("accepted", acc_list), ("rejected", rej_list), ("invalid", inv_list)):
            for resume in lst.list:
                label_by_file[resume.get_file] = label

        buckets: Dict[str, List[Dict[str, Any]]] = {"accepted": [], "rejected": [], "invalid": []}
        for entry in results:
            label = label_by_file.get(entry.get("file"), "invalid")
            # ResumeEvaluator.allocate only treats "scored with 0.0" as rejected, so the
            # AI's knockout rejections (outcome == "rejected") would land in invalid.
            if entry.get("outcome") == "rejected":
                label = "rejected"
            buckets[label].append({k: v for k, v in entry.items() if k != "text"})
        return buckets["accepted"], buckets["rejected"], buckets["invalid"]

    # ------------------------------------------------------------------ output
    @staticmethod
    def _package(accepted, rejected, invalid, summary_data) -> Dict[str, Any]:
        return {
            "ranked_candidates": accepted,
            "summary_data": summary_data,
            "filtered_resumes": {"accepted": accepted, "rejected": rejected, "invalid": invalid},
        }

    def _save_results(self, results: List[Dict[str, Any]]) -> None:
        stamp = datetime.now().strftime("%Y-%m-%d %H-%M-%S")
        path = self.output_dir / f"screening_results_{stamp}.json"
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2, ensure_ascii=False, default=str)
        except Exception as err:
            print(f"  [!] Could not save results: {err}")

    def generate_overview_report(self, summary_data: Dict[str, Any]) -> Path:
        """The report generator now reads the AI summary dict (AI mode only)."""
        if self.report_generator is None:
            raise RuntimeError("Overview report generator is unavailable.")
        return self.report_generator.generate_overview_report(summary_data)
