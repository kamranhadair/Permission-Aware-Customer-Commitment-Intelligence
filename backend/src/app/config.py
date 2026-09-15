from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    # `env_file` is an absolute path so this loads backend/.env regardless
    # of the process's current working directory (uvicorn, alembic, pytest
    # may all be invoked from different places). Real environment variables
    # still take precedence over values from the file.
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Required, not defaulted: a missing DATABASE_URL should fail loudly
    # at startup rather than silently running against a guessed local URL
    # that may not exist (or, worse, may exist and belong to someone else's
    # setup) on another machine.
    database_url: str


settings = Settings()
