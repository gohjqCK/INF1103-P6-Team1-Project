# Data Manager Cloud Integration Specification (`DATA_MANAGER_SPEC.md`)

This document defines the exact interface contract between the **I/O Manager (`TelegramIOManager` / `main.py`)** and the **Data Manager (`DataManager` / `SupabaseHandler`)**, aligned with the **existing 6 tables already live in your Supabase database**.

Right now, `TelegramIOManager` runs in **Cloud Stub (In-Memory) Mode** (`use_cloud=False`) because `DataManager.CLOUD_READY` is not yet set to `True`. Once the Data Manager implements the methods below against the live Supabase tables and sets `CLOUD_READY = True` on `DataManager`, the entire Telegram bot and screening pipeline will automatically switch to live Supabase Cloud storage with **zero edits needed in `io_manager_modules/`**.

---

## 1. Architecture & Handshake Overview

1. **No Local Company Files:** The app runs as a headless Telegram Server (`python main.py`). Users interact exclusively through Telegram. Do **not** depend on local `companies/` folders or `companies.json`.
2. **Automatic Switch-Over Flag:**
   Add `CLOUD_READY = True` as a class attribute on `DataManager` (`data_manager_modules/data_manager_side.py`) once all methods below are implemented.
   - `main.py` and `TelegramIOManager` check `getattr(data_mgr, "CLOUD_READY", False)`.
   - When `False` (default right now), `TelegramIOManager` uses its in-memory stub stores.
   - When `True`, `TelegramIOManager` calls the `DataManager` methods listed in Section 3.

---

## 2. Existing Live Supabase Schema & Storage Structure

Your Supabase database **already has these 6 tables** with foreign-key relationships in place:

| Table | Exact Columns Observed | Foreign Keys & Notes |
| :--- | :--- | :--- |
| **`users`** | `id`, `telegram_user_id`, `created_at` | Stores Telegram users. **Must exist before inserting `companies.owner_id`!** |
| **`companies`** | `id`, `name`, `invite_code`, `passcode_hash`, `owner_id`, `members`, `created_at` | `owner_id` -> FK to `users`. Note column is **`name`** (not `company_name`). |
| **`business_rules`** | `id`, `company_id`, `set_name`, `rules`, `created_at` | `company_id` -> FK to `companies.id`. Each row is a named **Rule Set** (e.g., `set_name = "Finance"`, `"Cleaners"`, `"Default"`) for that company, storing its rules JSON array in `rules`. |
| **`resume_files`** | `id`, `company_id`, `file_name`, `pdf_url`, `parsed_text`, `pages`, `status`, `invalid_reason`, `created_at`, `uploaded_at` | `company_id` -> FK to `companies.id`. Parsed text lives directly here (there is **no** `parsed_resumes` table—remove old calls to `parsed_resumes`). |
| **`results`** | `id`, `company_id`, `business_rules_id`, `filtered_resume`, `created_at` | `company_id` -> FK to `companies.id`, `business_rules_id` -> FK to `business_rules.id`. `filtered_resume` (singular!) stores `{ "accepted": [...], "rejected": [...], "invalid": [...], "ranked_candidates": [...] }`. |
| **`summaries`** | `id`, `result_id`, `summary`, `created_at` | `result_id` -> FK to `results.id`. Stores the `summary_data` JSON object in `summary`. |

### Storage & Constraint Checklist (Run / Verify in Supabase Dashboard)
1. **Add `set_name` Column to `business_rules` (Required Migration for Multi-Set Rule Sets):**
   Run this in the Supabase SQL Editor before testing Rule Sets:
   ```sql
   ALTER TABLE business_rules
       ADD COLUMN IF NOT EXISTS set_name TEXT NOT NULL DEFAULT 'Default';

   -- Enforce unique Rule Set names per company (case-sensitive or add citext/lower index if desired):
   ALTER TABLE business_rules
       DROP CONSTRAINT IF EXISTS uq_business_rules_company_set;
   ALTER TABLE business_rules
       ADD CONSTRAINT uq_business_rules_company_set UNIQUE (company_id, set_name);
   ```
2. **Storage Bucket (`resume_files`):** Confirm a Storage bucket named `resume_files` exists (and has Storage RLS policies allowing `SELECT`, `INSERT`, `UPDATE`, `DELETE` for the project key).
3. **Per-Company Storage Paths:** Store each PDF under `f"{company_id}/{file_name}"` (e.g. `1/john_cv.pdf`), not at the bucket root, so two companies never overwrite each other's files.
4. **Unique Constraints (Optional SQL check if needed):**
   - If `resume_files` currently has a global unique constraint on `file_name` alone, switch it to `(company_id, file_name)`:
     ```sql
     -- Run ONLY if two companies uploading the same filename causes a duplicate key error:
     -- ALTER TABLE resume_files DROP CONSTRAINT IF EXISTS resume_files_file_name_key;
     -- ALTER TABLE resume_files ADD CONSTRAINT uq_resume_company_file UNIQUE (company_id, file_name);
     ```
   - Ensure RLS policies on all 6 tables allow `SELECT`, `INSERT`, `UPDATE`, `DELETE` for the key in `.env`.

---

## 3. Required `DataManager` Methods & Return Formats

Implement these methods on `DataManager` in `data_manager_modules/data_manager_side.py` (backed by `SupabaseHandler` in `data_manager_modules/data_manager_supabase_handler.py`):

```python
class DataManager:
    CLOUD_READY = True  # Set to True once Supabase methods below are implemented
```

### A. User & Company Management (`users` + `companies`)

#### 1. `create_company(self, company_name: str, passcode_hash: str, owner_id: int, invite_code: str) -> Dict[str, Any]`
1. **Ensure user row exists first:** Upsert/lookup `owner_id` in `users` (`telegram_user_id = owner_id`) and get the `users.id` (or use `owner_id` depending on whether `companies.owner_id` references `users.id` or `users.telegram_user_id`—check the FK definition in Supabase).
2. **Insert into `companies`:** Map `company_name` -> column **`name`**, `invite_code`, `passcode_hash`, `owner_id`, `members: [owner_id]`.
3. *(Optional)* Upload `b""` to `f"{company_id}/.keep"` in Storage so the folder is visible immediately.
- **Raises:** `ValueError` if a company with that `name` already exists.
- **Returns** (note `"company_name"` key in the returned Python dict!):
  ```python
  {
      "company_id": 1,                  # int (companies.id)
      "company_name": "Acme Corp",      # str (from companies.name)
      "invite_code": "ACME-4821",       # str
      "passcode_hash": "<sha256_hex>",  # str
      "owner": 123456789,               # int (owner_id)
      "members": [123456789],           # list[int]
  }
  ```

#### 2. `get_company_by_invite(self, invite_code: str) -> Optional[Dict[str, Any]]`
Queries `companies` by case-insensitive `invite_code` (`.ilike("invite_code", invite_code.strip())`).
- **Returns:** Same dictionary format as `create_company` (mapping `row["name"]` -> `"company_name"` and `row["id"]` -> `"company_id"`), or `None` if not found.

#### 3. `add_company_member(self, company_id: int, user_id: int) -> None`
Ensures `user_id` exists in `users`, then appends `user_id` to `companies.members` for `id == company_id` if not already present.

---

### B. Business Rules Management (`business_rules` — Multi-Set per Company)

Each row in `business_rules` represents one named **Rule Set** for a company (`id`, `company_id`, `set_name`, `rules`, `created_at`).

**Rule Priority & Weight Validation Contract:**
Every rule dictionary stored in `rules` (JSON array) MUST include validated `text`, `priority`, and integer `weight`:
```python
PRIORITY_WEIGHTS = {
    "must": 4,
    "important": 3,
    "nice": 2,
    "can consider": 1,
    "reject": 0,
}
```
Validate on write (`create_company_rule_set`, `update_company_rule_set`) and normalize on read so every item matches:
```python
[
    {"text": "Minimum 3 years Python experience", "priority": "must", "weight": 4},
    {"text": "Experience with Docker", "priority": "important", "weight": 3},
]
```

#### 4. `list_company_rule_sets(self, company_id: int) -> List[Dict[str, Any]]`
Fetches all rows from `business_rules` where `company_id == company_id` (ordered by `id asc`).
- **Returns:** List of Rule Set dicts (or `[]` if none exist yet):
  ```python
  [
      {
          "rule_set_id": 10,             # int (business_rules.id)
          "company_id": 1,               # int
          "set_name": "Finance",         # str (business_rules.set_name)
          "rules": [
              {"text": "CPA or ACCA certified", "priority": "must", "weight": 4}
          ],
      },
      ...
  ]
  ```

#### 5. `create_company_rule_set(self, company_id: int, set_name: str, rules: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]`
Creates a new Rule Set row in `business_rules` for `company_id` with `set_name` (stripped, non-empty) and validated `rules` (default `[]`).
- **Raises:** `ValueError` if `set_name` is empty, if a Rule Set with the same name (case-insensitive) already exists for `company_id`, or if any rule has an invalid `priority`/weight.
- **Returns:** The created Rule Set dictionary (`{"rule_set_id": ..., "company_id": ..., "set_name": ..., "rules": [...]}`).

#### 6. `update_company_rule_set(self, company_id: int, rule_set_id: int, set_name: Optional[str] = None, rules: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]`
Updates an existing `business_rules` row where `id == rule_set_id` and `company_id == company_id`:
- If `set_name` is provided, checks uniqueness within `company_id` and updates `set_name`.
- If `rules` is provided, validates each rule's `text`, `priority`, and `weight` (`PRIORITY_WEIGHTS`) and updates `rules`.
- **Important:** Update the row **in place** rather than deleting & reinserting, so `business_rules.id` is preserved for `results.business_rules_id` foreign keys!
- **Returns:** The updated Rule Set dictionary (`{"rule_set_id": ..., "company_id": ..., "set_name": ..., "rules": [...]}`).

#### 7. `delete_company_rule_set(self, company_id: int, rule_set_id: int) -> bool`
Deletes the `business_rules` row where `id == rule_set_id` and `company_id == company_id` (and cascades/cleans up any `results` referencing `business_rules_id == rule_set_id` if FK is not `ON DELETE CASCADE`).
- **Returns:** `True` if deleted, `False` if not found.

---

### C. Resume Upload, Listing, Download & Deletion (`resume_files` + Storage)

#### 8. `upload_resume_bytes(self, file_name: str, pdf_bytes: bytes, company_id: Optional[int] = None) -> Dict[str, Any]`
*(Already exists — update it to match the live schema)*
1. Parses `pdf_bytes` with `self.parse_pdf_bytes(file_name, pdf_bytes)`.
2. Uploads to Storage (`resume_files` bucket) at path `f"{company_id}/{file_name}"`.
3. Upserts into `resume_files` table (`company_id`, `file_name`, `pdf_url`, `parsed_text`, `pages`, `status`, `invalid_reason`).
4. **Remove** the obsolete `export_parsed_resumes` call since `parsed_resumes` table does not exist in Supabase.
- **Returns:**
  ```python
  {
      "file": "john_cv.pdf",
      "file_name": "john_cv.pdf",
      "status": "valid",          # "valid" or "invalid"
      "reason": "",               # empty if valid, error string if invalid
      "pages": 2,
      "text": "<extracted text>",
      "pdf_url": "https://...",
      "company_id": 1,
      "source": "Supabase Cloud",
  }
  ```

#### 9. `list_company_resumes(self, company_id: int) -> List[Dict[str, Any]]`
Queries `resume_files` where `company_id == company_id`.
- **Returns:** List of dicts with keys:
  `"id"`, `"file"`, `"file_name"`, `"status"`, `"reason"` (from `invalid_reason`), `"pages"`, `"text"` (from `parsed_text`), `"pdf_url"`, `"source"` (`"Supabase Cloud"`).

#### 10. `download_resume_bytes(self, company_id: int, file_name: str) -> Optional[bytes]`
Downloads the raw PDF bytes from Supabase Storage path `f"{company_id}/{file_name}"` (or `None` if missing) so the Telegram bot can send the PDF directly to the user.

#### 11. `delete_company_resume(self, company_id: int, file_name: str) -> bool`
Deletes the file from Storage (`f"{company_id}/{file_name}"`) and its row in `resume_files` (`eq("company_id", company_id).eq("file_name", file_name)`). Returns `True` if deleted, `False` otherwise.

#### 12. `clear_company_resumes(self, company_id: int) -> None`
Deletes all resumes for `company_id` from Storage and `resume_files`.

---

### D. Results (`results`) & AI Summary (`summaries`) Persistence

#### 13. `save_screening_results(self, company_id: int, ranked_candidates: List[Dict[str, Any]], summary_data: Optional[Dict[str, Any]], filtered_resumes: Optional[Dict[str, Any]] = None, business_rules_id: Optional[int] = None) -> None`
1. Resolve `rule_row_id`: use `business_rules_id` directly when provided (the active Rule Set's `business_rules.id`); only fall back to querying the latest `business_rules.id` for `company_id` if `business_rules_id is None`.
2. Build the `filtered_resume` JSON payload:
   ```python
   payload = {
       "accepted": (filtered_resumes or {}).get("accepted", []),
       "rejected": (filtered_resumes or {}).get("rejected", []),
       "invalid": (filtered_resumes or {}).get("invalid", []),
       "ranked_candidates": ranked_candidates,
   }
   ```
3. Insert into **`results`** (`{"company_id": company_id, "business_rules_id": rule_row_id, "filtered_resume": payload}`) and read back the inserted `result_id = row["id"]`.
4. If `summary_data` is provided, insert into **`summaries`** (`{"result_id": result_id, "summary": summary_data}`).

#### 14. `get_screening_results(self, company_id: int, business_rules_id: Optional[int] = None) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]`
1. Query **`results`** where `company_id == company_id` (and **`.eq("business_rules_id", business_rules_id)` when `business_rules_id is not None`**), ordered by `created_at desc`, `limit 1`.
2. If none found, return `([], None)`.
3. Extract `fr = row.get("filtered_resume") or {}` -> `ranked = fr.get("ranked_candidates") or fr.get("accepted") or []`.
4. Query **`summaries`** where `result_id == row["id"]`, ordered by `created_at desc`, `limit 1` -> `summary_data = sum_row.get("summary")`.
5. Return `(ranked, summary_data)`.

---

## 4. Prompt to Give Your Data Manager Teammate's AI

Copy and paste the prompt below to the AI assisting your Data Manager teammate:

> We updated our project so the entire app runs as a Telegram Bot Server (`main.py` + `io_manager_modules/io_manager_telegram.py`), and we just added **multi-set Business Rules per company** (e.g., `"Finance"`, `"Cleaners"`), in-place rule editing with strict weight validation (`must: 4`, `important: 3`, `nice: 2`, `can consider: 1`, `reject: 0`), and Rule Set-scoped screening results (`results.business_rules_id`).
>
> Please read `DATA_MANAGER_SPEC.md`, `data_manager_modules/data_manager_side.py`, and `data_manager_modules/data_manager_supabase_handler.py`, then:
> 1. Implement all 14 methods specified in Section 3 of `DATA_MANAGER_SPEC.md` on `DataManager` and `SupabaseHandler` using our exact existing column names (`companies.name`, `business_rules.set_name`, `business_rules.rules`, `results.filtered_resume`, `results.business_rules_id`, `summaries.result_id`, `summaries.summary`, and `users.telegram_user_id` before `companies.owner_id`).
> 2. Implement the 4 Rule Set methods (`list_company_rule_sets`, `create_company_rule_set`, `update_company_rule_set`, `delete_company_rule_set`), validating each rule's `"priority"` and integer `"weight"` (`must=4`, `important=3`, `nice=2`, `can consider=1`, `reject=0`) and updating `business_rules` rows **in place** so `business_rules.id` stays intact for `results.business_rules_id`.
> 3. Update `save_screening_results` and `get_screening_results` to accept `business_rules_id: Optional[int] = None` so results and summaries are scoped to the active Rule Set.
> 4. Remove obsolete calls to the deleted `parsed_resumes` table (use `resume_files` columns directly) and scope all Storage uploads under `f"{company_id}/{file_name}"` in the `resume_files` bucket.
> 5. Set `CLOUD_READY = True` on `DataManager` once everything is implemented so `TelegramIOManager` and `main.py` automatically switch from stub mode to Supabase Cloud mode.
> 6. Remind me to run the `ALTER TABLE business_rules ADD COLUMN IF NOT EXISTS set_name ...` SQL migration from Section 2 and tell me if any Supabase Storage bucket or RLS policy needs to be adjusted.
> 7. Do NOT modify any files in `io_manager_modules/` or `main.py`.

---

## 5. Adding Future Data Types / Tables (2-Step Extensibility Pattern)

Whenever your team wants to store something new in Supabase (e.g., job postings, interview schedules, audit logs, or candidate notes):

1. **Data Manager side (`data_manager_side.py` & `data_manager_supabase_handler.py`):**
   - Create the new Supabase table with `company_id BIGINT NOT NULL REFERENCES companies(id) ON DELETE CASCADE`.
   - Add two clean methods on `DataManager` (e.g., `save_<feature>(self, company_id: int, data: ...)` and `get_<feature>(self, company_id: int)`).
2. **I/O Manager side (`io_manager_telegram.py`):**
   - Add a matching `_dm_save_<feature>` / `_dm_get_<feature>` bridge method that checks `if self._use_cloud and hasattr(self._data_manager, "...")` with an in-memory stub dictionary fallback, then wire a button in `TelegramKeyboards`.
