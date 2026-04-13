import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    entsoe_api_token: str = ""

    postgres_user: str = "gridlog"
    postgres_password: str = "gridlog"
    postgres_db: str = "gridlog"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    @property
    def timedb_dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()

# TimeDB resolves its connection from TIMEDB_DSN / DATABASE_URL at call time.
# Exporting it here means every import site gets a configured client for free.
os.environ.setdefault("TIMEDB_DSN", settings.timedb_dsn)
