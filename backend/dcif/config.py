from __future__ import annotations

from pathlib import Path

import yaml

from backend.dcif.models import CrawlConfig
from backend.dcif.paths import config_path


DEFAULT_CONFIG_PATH = config_path("sources.yaml")


def load_crawl_config(path: Path = DEFAULT_CONFIG_PATH) -> CrawlConfig:
    with path.open("r", encoding="utf-8") as handle:
        return CrawlConfig.model_validate(yaml.safe_load(handle))
