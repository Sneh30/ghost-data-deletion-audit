"""Load all participant-facing CSVs and the evidence manifest."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .util import norm_email, parse_ts, sha256_email


@dataclass
class Dataset:
    root: Path
    requests: pd.DataFrame
    sample_requests: pd.DataFrame
    sample_output: pd.DataFrame
    identities: pd.DataFrame
    audit_log: pd.DataFrame
    activity: pd.DataFrame
    rules: pd.DataFrame
    manifest: pd.DataFrame
    evidence_dir: Path
    _by_email: dict[str, list[str]] = field(default_factory=dict)
    _by_user: dict[str, dict] = field(default_factory=dict)

    def __post_init__(self) -> None:
        ids = self.identities.copy()
        ids["email_norm"] = ids["email"].map(norm_email)
        for row in ids.to_dict("records"):
            self._by_email.setdefault(row["email_norm"], []).append(row["user_id"])
            self._by_user[row["user_id"]] = {
                "user_id": row["user_id"],
                "name": row["name"],
                "email": row["email"],
                "phone": row["phone"],
                "email_hash": row["email_hash"],
                "updated_at": row["updated_at"],
            }

    def evidence_path(self, file_id: str) -> Path:
        row = self.manifest[self.manifest.file_id == file_id].iloc[0]
        return self.root / "dataset" / row.file_path


def load_dataset(root: Path | str) -> Dataset:
    root = Path(root)
    ds = root / "dataset"
    read = lambda name: pd.read_csv(ds / name, dtype=str, keep_default_na=False)
    return Dataset(
        root=root,
        requests=read("deletion_requests.csv"),
        sample_requests=read("sample_deletion_requests.csv"),
        sample_output=read("sample_output.csv"),
        identities=read("user_identities.csv"),
        audit_log=read("user_audit_log.csv"),
        activity=read("system_activity.csv"),
        rules=read("deletion_rules.csv"),
        manifest=read("evidence_files.csv"),
        evidence_dir=ds / "evidence",
    )


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))
