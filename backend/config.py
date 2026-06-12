import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional fallback for minimal environments
    load_dotenv = None


BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent


def _load_env_files() -> None:
    """Load env files."""
    if load_dotenv is None:
        return
    load_dotenv(PROJECT_ROOT / ".env")
    load_dotenv(BACKEND_DIR / ".env")


def _legacy_data_root_unused() -> Path:
    """保留现有项目的自动路径探测逻辑，作为 .env 未配置时的 fallback。"""
    if os.name == "nt":
        candidates = [
            Path("G:/我的云端硬盘/TBM9"),
            Path("G:/My Drive/TBM9"),
        ]
        for path in candidates:
            try:
                if path.exists():
                    return path
            except PermissionError:
                continue

    cloud_base = Path.home() / "Library/CloudStorage"
    if cloud_base.exists():
        drives = list(cloud_base.glob("GoogleDrive*"))
        for drive in drives:
            for root_name in ["我的云端硬盘", "My Drive"]:
                path = drive / root_name / "TBM9"
                if path.exists():
                    return path

    return BACKEND_DIR / "data"


def _legacy_data_root() -> Path:
    """Keep legacy auto-detection only as a fallback when DATA_ROOT is unset."""
    if os.name == "nt":
        for path in [Path("G:/我的云端硬盘/TBM9"), Path("G:/My Drive/TBM9")]:
            try:
                if path.exists():
                    return path
            except PermissionError:
                continue

    cloud_base = Path.home() / "Library/CloudStorage"
    if cloud_base.exists():
        for drive in cloud_base.glob("GoogleDrive*"):
            for root_name in ["我的云端硬盘", "My Drive"]:
                path = drive / root_name / "TBM9"
                if path.exists():
                    return path

    return BACKEND_DIR / "data"


def _resolve_path_env(name: str, default: Path) -> Path:
    """Resolve path env."""
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    value = Path(raw).expanduser()
    if not value.is_absolute():
        value = PROJECT_ROOT / value
    return value


def _resolve_float_env(name: str, default: float) -> float:
    """Resolve float env."""
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _resolve_bool_env(name: str, default: bool) -> bool:
    """Resolve bool env."""
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "y", "on"}:
        return True
    if raw in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _resolve_list_env(name: str, default: list[str]) -> list[str]:
    """Resolve comma-separated list env."""
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    values = [item.strip() for item in raw.split(",") if item.strip()]
    return values or default


_load_env_files()

CONFIG_WARNINGS: list[str] = []
_DATA_ROOT_ENV_RAW = os.getenv("DATA_ROOT", "").strip()
DATA_ROOT = _resolve_path_env("DATA_ROOT", _legacy_data_root())
if not _DATA_ROOT_ENV_RAW:
    CONFIG_WARNINGS.append(
        f"DATA_ROOT is not set; using fallback DATA_ROOT={DATA_ROOT}. "
        "Set DATA_ROOT in backend/.env or project .env for reproducible runs."
    )
DATA_DIR = _resolve_path_env("DATA_DIR", DATA_ROOT / "TBM9_2023")
TSP_DIR = _resolve_path_env("TSP_DIR", DATA_ROOT / "TSP")
HSP_DIR = _resolve_path_env("HSP_DIR", DATA_ROOT / "HSP")
SKETCH_DIR = _resolve_path_env("SKETCH_DIR", DATA_ROOT / "SKETCH")
DRILL_DIR = _resolve_path_env("DRILL_DIR", DATA_ROOT / "DRILL")

DB_DIR = _resolve_path_env("DB_DIR", DATA_ROOT / "DB")
RESULT_DIR = _resolve_path_env("RESULT_DIR", DATA_ROOT / "result")
LOG_DIR = _resolve_path_env("LOG_DIR", DATA_ROOT / "logs")
DAILY_RESULT_DIR = _resolve_path_env("DAILY_RESULT_DIR", DATA_ROOT / "result_daily_twin")
HISTORY_MEMORY_DIR = _resolve_path_env("HISTORY_MEMORY_DIR", DATA_ROOT / "analysis_history")

APP_DB_PATH = _resolve_path_env("APP_DB_PATH", DB_DIR / "tbm_app.sqlite3")
EVIDENCE_DB_PATH = _resolve_path_env("EVIDENCE_DB_PATH", DB_DIR / "evidence_db.csv")

# Dev default keeps previous behavior. Set ENSURE_DIRS_ON_IMPORT=false for read-only/prod environments.
ENSURE_DIRS_ON_IMPORT = _resolve_bool_env("ENSURE_DIRS_ON_IMPORT", True)
if ENSURE_DIRS_ON_IMPORT:
    for directory in [DB_DIR, RESULT_DIR, LOG_DIR, DAILY_RESULT_DIR, HISTORY_MEMORY_DIR, APP_DB_PATH.parent]:
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            CONFIG_WARNINGS.append(
                f"Cannot create or inspect directory {directory}; check DATA_ROOT permissions "
                "or set ENSURE_DIRS_ON_IMPORT=false for read-only runs."
            )

TOLERANCE_M = _resolve_float_env("TOLERANCE_M", 3.0)
HIGH_RISK_LOOKAHEAD_M = _resolve_float_env("HIGH_RISK_LOOKAHEAD_M", 10.0)
NEXT_FORECAST_LOOKAHEAD_M = _resolve_float_env("NEXT_FORECAST_LOOKAHEAD_M", 5.0)

# FastAPI / deployment
CORS_ALLOW_ORIGINS = _resolve_list_env("CORS_ALLOW_ORIGINS", ["*"])
CORS_ALLOW_CREDENTIALS = _resolve_bool_env("CORS_ALLOW_CREDENTIALS", True)
