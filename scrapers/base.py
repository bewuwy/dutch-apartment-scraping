"""Base scraper interface."""

from abc import ABC, abstractmethod
from typing import List, Dict, Any
from models import Listing


class BaseScraper(ABC):
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.tenant_profile = config.get("tenant_profile", {})
        self.search_criteria = config.get("search_criteria", {})

    @abstractmethod
    def scrape(self) -> List[Listing]:
        """Scrape listings matching search criteria."""
        pass
