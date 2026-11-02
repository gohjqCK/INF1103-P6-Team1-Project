"""Main script entry point for Data Manager pipeline."""
from data_manager_modules.data_manager_side import DataManager

if __name__ == "__main__":
    manager = DataManager()
    manager.process_all_resumes()