from dataclasses import dataclass
from datetime import datetime
from typing import List, Dict, Optional
import hashlib


@dataclass
class Article:
    """Data class representing a Solutions Story article"""
    title: str
    url: str
    outlet: str
    issue_area: str
    id: Optional[int] = None
    scraped_at: Optional[datetime] = None
    excluded: bool = False

    @property
    def url_hash(self) -> str:
        """Generate URL hash for deduplication"""
        return hashlib.md5(self.url.encode()).hexdigest()

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization"""
        return {
            'id': self.id,
            'title': self.title,
            'url': self.url,
            'outlet': self.outlet,
            'issue_area': self.issue_area,
            'scraped_at': self.scraped_at.isoformat() if self.scraped_at else None,
            'excluded': self.excluded
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'Article':
        """Create Article from dictionary"""
        scraped_at = None
        if data.get('scraped_at'):
            scraped_at = datetime.fromisoformat(data['scraped_at'])

        return cls(
            title=data['title'],
            url=data['url'],
            outlet=data['outlet'],
            issue_area=data['issue_area'],
            id=data.get('id'),
            scraped_at=scraped_at,
            excluded=data.get('excluded', False)
        )


@dataclass
class Subscriber:
    """Data class representing a subscriber"""
    email: str
    issue_area: str
    cadence: str = 'weekly'
    preferred_day: str = 'Monday'
    preferred_hour: int = 9
    active: bool = True
    id: Optional[int] = None
    last_sent: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @property
    def issue_areas(self) -> List[str]:
        """Get list of subscriber's issue areas"""
        return [self.issue_area]

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization"""
        return {
            'id': self.id,
            'email': self.email,
            'issue_area': self.issue_area,
            'cadence': self.cadence,
            'preferred_day': self.preferred_day,
            'preferred_hour': self.preferred_hour,
            'last_sent': self.last_sent.isoformat() if self.last_sent else None,
            'active': self.active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'Subscriber':
        """Create Subscriber from dictionary"""
        created_at = None
        updated_at = None
        last_sent = None

        if data.get('created_at'):
            created_at = datetime.fromisoformat(data['created_at'])
        if data.get('updated_at'):
            updated_at = datetime.fromisoformat(data['updated_at'])
        if data.get('last_sent'):
            last_sent = datetime.fromisoformat(data['last_sent'])

        return cls(
            email=data['email'],
            issue_area=data['issue_area'],
            cadence=data.get('cadence', 'weekly'),
            preferred_day=data.get('preferred_day', 'Monday'),
            preferred_hour=data.get('preferred_hour', 9),
            active=data.get('active', True),
            id=data.get('id'),
            last_sent=last_sent,
            created_at=created_at,
            updated_at=updated_at
        )


@dataclass
class EmailCampaign:
    """Data class representing an email campaign"""
    campaign_type: str  # 'scheduled' or 'manual'
    status: str = 'pending'  # 'pending', 'sent', 'failed'
    id: Optional[int] = None
    scheduled_for: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    total_recipients: int = 0
    articles_sent: Optional[List[int]] = None
    created_by: str = 'admin'
    notes: str = ''

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization"""
        return {
            'id': self.id,
            'campaign_type': self.campaign_type,
            'status': self.status,
            'scheduled_for': self.scheduled_for.isoformat() if self.scheduled_for else None,
            'sent_at': self.sent_at.isoformat() if self.sent_at else None,
            'total_recipients': self.total_recipients,
            'articles_sent': self.articles_sent,
            'created_by': self.created_by,
            'notes': self.notes
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'EmailCampaign':
        """Create EmailCampaign from dictionary"""
        scheduled_for = None
        sent_at = None

        if data.get('scheduled_for'):
            scheduled_for = datetime.fromisoformat(data['scheduled_for'])
        if data.get('sent_at'):
            sent_at = datetime.fromisoformat(data['sent_at'])

        return cls(
            campaign_type=data['campaign_type'],
            status=data.get('status', 'pending'),
            id=data.get('id'),
            scheduled_for=scheduled_for,
            sent_at=sent_at,
            total_recipients=data.get('total_recipients', 0),
            articles_sent=data.get('articles_sent'),
            created_by=data.get('created_by', 'admin'),
            notes=data.get('notes', '')
        )


class FallbackManager:
    """Manages fallback categories for when articles are scarce"""

    # Define fallback mappings - if primary category has insufficient articles,
    # try these related categories
    FALLBACK_MAPPING = {
        'Health': ['Mental Health', 'Community Development'],
        'Mental Health': ['Health', 'Social Services'],
        'Housing': ['Economic Development', 'Community Development'],
        'Environment': ['Energy', 'Agriculture', 'Public Safety'],
        'Criminal Justice': ['Public Safety', 'Community Development', 'Mental Health'],
        'Economic Development': ['Housing', 'Workforce Development', 'Community Development'],
        'Democracy & Governance': ['Public Safety', 'Community Development'],
        'Immigration': ['Social Services', 'Community Development'],
        'Transportation': ['Infrastructure', 'Public Safety', 'Environment'],
        'Food Security': ['Agriculture', 'Community Development', 'Health'],
        'Community Development': ['Social Services', 'Economic Development'],
        'Technology': ['Education', 'Infrastructure'],
        'Energy': ['Environment', 'Infrastructure'],
        'Agriculture': ['Food Security', 'Environment', 'Economic Development'],
        'Social Services': ['Community Development', 'Mental Health'],
        'Arts & Culture': ['Community Development', 'Education'],
        'Youth Development': ['Education', 'Community Development'],
        'Senior Services': ['Health', 'Social Services'],
        'Public Safety': ['Criminal Justice', 'Community Development'],
        'Infrastructure': ['Transportation', 'Economic Development'],
        'Workforce Development': ['Economic Development', 'Education']
    }

    @classmethod
    def get_fallback_categories(cls, primary_category: str, max_fallbacks: int = 3) -> List[str]:
        """Get fallback categories for a primary category"""
        return cls.FALLBACK_MAPPING.get(primary_category, [])[:max_fallbacks]

    @classmethod
    def get_all_related_categories(cls, primary_category: str) -> List[str]:
        """Get primary category plus all fallbacks"""
        fallbacks = cls.get_fallback_categories(primary_category)
        return [primary_category] + fallbacks


class ArticleSelector:
    """Handles smart article selection with fallbacks"""

    def __init__(self, db_manager):
        self.db = db_manager
        self.fallback_manager = FallbackManager()

    def select_articles_for_subscriber(self, subscriber: Subscriber, articles_per_category: int = 1) -> Dict[
        str, List[Article]]:
        """
        Select articles for subscriber with fallback logic
        Returns dict mapping issue_area -> list of selected articles
        """
        selected_articles = {}
        fallback_used = {}

        for issue_area in subscriber.issue_areas:
            articles = self._get_articles_with_fallback(
                subscriber.id,
                issue_area,
                articles_per_category
            )

            if articles:
                selected_articles[issue_area] = articles
                # Track if we used fallback categories
                primary_articles = [a for a in articles if a.issue_area == issue_area]
                if len(primary_articles) < len(articles):
                    fallback_used[issue_area] = True
            else:
                # No articles found even with fallbacks
                selected_articles[issue_area] = []
                fallback_used[issue_area] = True

        # Store fallback usage info for email generation
        self.last_fallback_usage = fallback_used

        return selected_articles

    def _get_articles_with_fallback(self, subscriber_id: int, primary_category: str, needed_count: int) -> List[
        Article]:
        """Get articles for category with fallback logic, shuffing for random selection"""
        import random
        all_categories = self.fallback_manager.get_all_related_categories(primary_category)
        selected_articles = []

        # Get fresh articles for all related categories
        articles_by_category = self.db.get_fresh_articles_for_subscriber(
            subscriber_id,
            all_categories
        )

        # First, try to get articles from primary category
        primary_articles = articles_by_category.get(primary_category, [])
        
        # Shuffle the primary articles to select a random subset
        random.shuffle(primary_articles)
        
        for article_data in primary_articles[:needed_count]:
            selected_articles.append(Article.from_dict(article_data))

        # If we need more articles, use fallback categories
        if len(selected_articles) < needed_count:
            fallback_categories = self.fallback_manager.get_fallback_categories(primary_category)

            for fallback_category in fallback_categories:
                if len(selected_articles) >= needed_count:
                    break

                fallback_articles = articles_by_category.get(fallback_category, [])
                
                # Shuffle fallback articles as well for random sampling
                random.shuffle(fallback_articles)
                
                remaining_needed = needed_count - len(selected_articles)

                for article_data in fallback_articles[:remaining_needed]:
                    selected_articles.append(Article.from_dict(article_data))

        return selected_articles

    def was_fallback_used(self, issue_area: str) -> bool:
        """Check if fallback was used for a specific issue area in last selection"""
        return getattr(self, 'last_fallback_usage', {}).get(issue_area, False)


# Available issue areas - centralized definition
AVAILABLE_ISSUE_AREAS = [
    'Education', 'Health', 'Housing', 'Environment', 'Criminal Justice',
    'Economic Development', 'Democracy & Governance', 'Immigration', 'Transportation',
    'Food Security', 'Mental Health', 'Community Development', 'Technology',
    'Energy', 'Agriculture', 'Social Services', 'Arts & Culture', 'Youth Development',
    'Senior Services', 'Public Safety', 'Infrastructure', 'Workforce Development'
]