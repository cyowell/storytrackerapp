import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime
from typing import List, Optional, Dict, Tuple
from urllib.parse import urlparse, urljoin

from src.models.database import DatabaseManager
from src.models.article import Article, AVAILABLE_ISSUE_AREAS


class SolutionsStoryScraper:
    """Handles scraping articles from Solutions Story Tracker website"""

    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self.base_url = "https://storytracker.solutionsjournalism.org/"
        self.session = requests.Session()
        self.session.headers.update(self.get_default_headers())

    def get_default_headers(self) -> Dict[str, str]:
        """Get default headers for requests"""
        return {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }

    def scrape_articles_for_issue(self, issue_area: str, limit: int = 10) -> List[Article]:
        """
        Scrape articles for a specific issue area
        Returns list of Article objects
        """
        try:
            # Build search request for specific issue area using GET parameters
            if issue_area and issue_area != 'All Issues':
                import urllib.parse
                quoted_issue = urllib.parse.quote(issue_area)
                url = f"{self.base_url}?issue-areas%5B%5D={quoted_issue}&page=1&search_stories=Search"
                response = self.session.get(url, timeout=15)
            else:
                response = self.session.get(self.base_url, timeout=15)

            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')

            # Find story links
            story_links = self._find_story_links(soup)

            print(f"Found {len(story_links)} story links for {issue_area}")

            articles = []
            processed_count = 0

            for link in story_links:
                if processed_count >= limit:
                    break

                try:
                    story_tracker_url = self._build_full_url(link.get('href', ''))
                    if not story_tracker_url:
                        continue

                    title = self._clean_title(link.get_text().strip())
                    if not title or len(title) < 10:
                        continue

                    # Get original article URL and outlet info
                    original_url, outlet = self._extract_original_article_info(story_tracker_url)

                    if original_url:
                        article = Article(
                            title=title,
                            url=original_url,
                            outlet=outlet,
                            issue_area=issue_area,
                            scraped_at=datetime.now()
                        )

                        # Add to database and get ID
                        article_id = self.db.add_article(
                            title=article.title,
                            url=article.url,
                            outlet=article.outlet,
                            issue_area=article.issue_area
                        )

                        if article_id:
                            article.id = article_id
                            articles.append(article)
                            processed_count += 1
                            print(f"Added article: {title[:50]}...")

                    # Rate limiting
                    time.sleep(0.5)

                except Exception as e:
                    print(f"Error processing story link: {e}")
                    continue

            return articles

        except Exception as e:
            print(f"Error scraping articles for {issue_area}: {e}")
            return []

    def _find_story_links(self, soup: BeautifulSoup) -> List:
        """Find story links in the HTML soup"""
        # Look for story links - adjust selectors based on actual site structure
        story_links = []

        # Try multiple selectors to find story links including new '/stories/' path
        selectors = [
            'a[href*="/stories/"]',
            'a[href*="/story/"]',
            '.story__title a',
            '.story-title a',
            '.story-link',
            'h1 a',
            'h3 a'
        ]

        for selector in selectors:
            links = soup.select(selector)
            if links:
                story_links.extend(links)

        # Remove duplicates while preserving order
        seen_urls = set()
        unique_links = []
        for link in story_links:
            href = link.get('href', '')
            if href and href not in seen_urls:
                seen_urls.add(href)
                unique_links.append(link)

        return unique_links

    def _build_full_url(self, href: str) -> Optional[str]:
        """Build full URL from relative href"""
        if not href:
            return None

        if href.startswith('http'):
            return href

        return urljoin(self.base_url, href)

    def _clean_title(self, title: str) -> str:
        """Clean and normalize article title"""
        if not title:
            return ""

        # Remove extra whitespace and newlines
        title = ' '.join(title.split())

        # Remove common prefixes/suffixes
        prefixes_to_remove = ['Story: ', 'Article: ', 'News: ']
        for prefix in prefixes_to_remove:
            if title.startswith(prefix):
                title = title[len(prefix):]

        return title.strip()

    def _extract_original_article_info(self, story_tracker_url: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Extract original article URL and outlet from story tracker page
        Returns tuple of (original_url, outlet)
        """
        try:
            response = self.session.get(story_tracker_url, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')

            original_url = None
            outlet = None

            # 1. Target "Go to Original Story" link explicitly
            for link in soup.find_all('a'):
                text = link.get_text(strip=True)
                if 'Go to Original Story' in text:
                    original_url = link.get('href', '')
                    # Try to parse outlet from sibling/meta tags or url
                    outlet = self._extract_outlet_from_url(original_url)
                    break

            # 2. Fallback to old selectors if not found
            if not original_url:
                selectors = [
                    'a[href*="://"]',  # External links
                    '.original-link a',
                    '.source-link a',
                    '.article-link a'
                ]

                for selector in selectors:
                    links = soup.select(selector)
                    for link in links:
                        href = link.get('href', '')
                        if href and not href.startswith(self.base_url) and '://' in href:
                            original_url = href
                            outlet = self._extract_outlet_from_url(href) or link.get_text().strip()
                            break
                    if original_url:
                        break

            # Fallback for outlet: Look at text content or inline meta info
            if not outlet:
                outlet_selectors = [
                    '.outlet',
                    '.source',
                    '.publication'
                ]
                for selector in outlet_selectors:
                    outlet_elem = soup.select_one(selector)
                    if outlet_elem:
                        outlet = outlet_elem.get_text().strip()
                        break

            return original_url, outlet

        except Exception as e:
            print(f"Error extracting original article info from {story_tracker_url}: {e}")
            return None, None

    def _extract_outlet_from_url(self, url: str) -> Optional[str]:
        """Extract outlet name from URL"""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()

            # Remove common prefixes
            if domain.startswith('www.'):
                domain = domain[4:]

            # Extract main domain name
            parts = domain.split('.')
            if len(parts) >= 2:
                outlet_name = parts[0]

                # Capitalize and clean up
                outlet_name = outlet_name.replace('-', ' ').title()

                # Handle known outlets
                outlet_mapping = {
                    'nytimes': 'The New York Times',
                    'washingtonpost': 'The Washington Post',
                    'cnn': 'CNN',
                    'bbc': 'BBC',
                    'npr': 'NPR',
                    'reuters': 'Reuters',
                    'ap': 'Associated Press',
                    'usatoday': 'USA Today'
                }

                return outlet_mapping.get(outlet_name.lower().replace(' ', ''), outlet_name)

            return None

        except Exception:
            return None

    def scrape_all_issue_areas(self, articles_per_issue: int = 5) -> Dict[str, List[Article]]:
        """
        Scrape articles for all available issue areas
        Returns dict mapping issue_area -> list of articles
        """
        all_articles = {}

        for issue_area in AVAILABLE_ISSUE_AREAS:
            print(f"\nScraping articles for: {issue_area}")
            articles = self.scrape_articles_for_issue(issue_area, articles_per_issue)
            all_articles[issue_area] = articles

            # Rate limiting between issue areas
            time.sleep(1)

        return all_articles

    def get_recent_articles_count(self, days: int = 7) -> Dict[str, int]:
        """Get count of recently scraped articles by issue area"""
        from datetime import timedelta

        cutoff_date = datetime.now() - timedelta(days=days)

        conn = self.db.get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT issue_area, COUNT(*) 
            FROM articles 
            WHERE scraped_at >= ? AND excluded = 0
            GROUP BY issue_area
            ORDER BY issue_area
        ''', (cutoff_date,))

        results = dict(cursor.fetchall())
        conn.close()

        return results

    def cleanup_old_articles(self, days_to_keep: int = 90) -> int:
        """
        Remove articles older than specified days (except those already sent)
        Returns number of articles removed
        """
        from datetime import timedelta

        cutoff_date = datetime.now() - timedelta(days=days_to_keep)

        conn = self.db.get_connection()
        cursor = conn.cursor()

        # Only delete articles that haven't been sent to anyone
        cursor.execute('''
            DELETE FROM articles 
            WHERE scraped_at < ? 
            AND id NOT IN (SELECT DISTINCT article_id FROM article_sends)
        ''', (cutoff_date,))

        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()

        print(f"Cleaned up {deleted_count} old articles")
        return deleted_count