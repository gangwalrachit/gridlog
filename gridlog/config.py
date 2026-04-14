"""GridLog runtime configuration."""

import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    entsoe_api_token: str = ""

    # Dev defaults match docker-compose.yml; real values come from .env.
    postgres_user: str = "gridlog"
    postgres_password: str = "gridlog"
    postgres_db: str = "gridlog"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    @property
    def timedb_dsn(self) -> str:
        """Postgres DSN (connection URL) consumed by TimeDB."""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()

# TimeDB reads TIMEDB_DSN at connect time; setdefault lets ambient env win.
os.environ.setdefault("TIMEDB_DSN", settings.timedb_dsn)
