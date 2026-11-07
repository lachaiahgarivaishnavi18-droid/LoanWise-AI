from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field,model_validator
from typing import Literal


class Settings(BaseSettings):
    database_url: str | None = None
    postgres_host: str | None = None
    postgres_user: str = 'loanwise'
    postgres_password: str = Field(default='',repr=False)
    postgres_db: str = 'loanwise'
    postgres_port: int = 5432
    demo_mode: bool = True
    cookie_secure: bool = False
    allowed_origin: str = 'http://127.0.0.1:5173'
    storage_dir: str = 'runtime/documents'
    document_storage: Literal['filesystem','database'] = 'filesystem'
    model_dir: str = 'runtime/models'
    runtime_dir: str = 'runtime'
    data_dir: str = 'data'
    llm_provider: Literal['local','local-api','openai','openai-compatible','gemini','anthropic'] = 'local'
    llm_api_key: str = ''
    llm_model: str = ''
    llm_base_url: str = 'https://api.openai.com/v1'
    retrieval_mode: Literal['local','neural'] = 'local'
    neural_min_similarity: float = Field(default=.25,ge=0,le=1)
    model_feature_policies: dict[str,list[Literal['dti','lti','employment_months','credit_utilization','missed_payments']]] = Field(default_factory=lambda:{'SYNTHETIC DEMO':['dti','lti','employment_months','credit_utilization','missed_payments']})
    embedding_model: str = 'sentence-transformers/all-MiniLM-L6-v2'
    reranker_model: str = 'cross-encoder/ms-marco-MiniLM-L-6-v2'
    session_hours: int = Field(default=8,ge=1,le=168)
    retention_days: int = Field(default=90,ge=1,le=3650)
    risk_low_threshold: float = 0.3
    risk_high_threshold: float = 0.6
    ocr_enabled: bool = True
    ocr_max_pages: int = Field(default=20,ge=1,le=200)
    ocr_max_pixels: int = Field(default=20_000_000,ge=1_000_000,le=40_000_000)
    parser_timeout_seconds: int = Field(default=60,ge=5,le=300)
    parser_memory_mb: int = Field(default=2048,ge=512,le=8192)
    parser_process_mode: Literal['spawn','subprocess'] = 'spawn'
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

    @model_validator(mode='after')
    def configure_database(self):
        if self.database_url and self.database_url.startswith(('postgres://','postgresql://')):
            self.database_url='postgresql+psycopg://'+self.database_url.split('://',1)[1]
        if self.database_url is None:
            if self.postgres_host:
                from sqlalchemy.engine import URL
                self.database_url=URL.create('postgresql+psycopg',username=self.postgres_user,password=self.postgres_password,host=self.postgres_host,port=self.postgres_port,database=self.postgres_db).render_as_string(hide_password=False)
            else:
                self.database_url='sqlite:///./runtime/loanwise.db'
        if not 0<=self.risk_low_threshold<self.risk_high_threshold<=1:
            raise ValueError('Risk thresholds must satisfy 0 <= low < high <= 1')
        return self


settings = Settings()
