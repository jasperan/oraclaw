import re

from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import Optional, Literal


class OraclawSettings(BaseSettings):
    oracle_mode: Literal["freepdb", "adb"] = "freepdb"
    oracle_user: str = "oraclaw"
    oracle_password: str = ""
    oracle_host: str = "localhost"
    oracle_port: int = 1521
    oracle_service: str = "FREEPDB1"
    oracle_dsn: Optional[str] = None
    oracle_wallet_path: Optional[str] = None
    oracle_wallet_password: Optional[str] = None
    oracle_pool_min: int = 2
    oracle_pool_max: int = 10
    oracle_onnx_model: str = "ALL_MINILM_L12_V2"
    oraclaw_service_port: int = 8100
    oraclaw_service_token: Optional[str] = None
    auto_init: bool = False

    model_config = {"env_prefix": "", "case_sensitive": False}

    @field_validator("oracle_onnx_model")
    @classmethod
    def validate_onnx_model(cls, v: str) -> str:
        if not re.match(r"^[A-Za-z0-9_]+$", v):
            raise ValueError(f"Invalid ONNX model name: {v!r} (alphanumeric and underscores only)")
        return v

    def get_dsn(self) -> str:
        if self.oracle_mode == "adb" and self.oracle_dsn:
            return self.oracle_dsn
        return f"{self.oracle_host}:{self.oracle_port}/{self.oracle_service}"
