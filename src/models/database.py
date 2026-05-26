import sqlite3
import hashlib
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import json


class DatabaseManager:
    """Manages all database operations for the Story Tracker app"""

    def __init__(self, db_path='story_tracker.db'):
        self.db_path = db_path
        self.init_database()

    def init_database(self):
        """Initialize all database tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Subscribers table - tracks email list, issue area, cadence, and last sent timestamp
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS subscribers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                issue_area TEXT NOT NULL,
                cadence TEXT NOT NULL DEFAULT 'weekly',
                last_sent TIMESTAMP,
                active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Articles table - tracks all scraped articles with unique identifiers
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url_hash TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                outlet TEXT,
                issue_area TEXT NOT NULL,
                scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                excluded BOOLEAN DEFAULT 0
            )
        ''')

        # Email campaigns - tracks scheduled and sent campaigns
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS email_campaigns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_type TEXT NOT NULL, -- 'scheduled' or 'manual'
                status TEXT DEFAULT 'pending', -- 'pending', 'sent', 'failed'
                scheduled_for TIMESTAMP,
                sent_at TIMESTAMP,
                total_recipients INTEGER DEFAULT 0,
                articles_sent TEXT, -- JSON array of article IDs
                created_by TEXT DEFAULT 'admin',
                notes TEXT
            )
        ''')

        # Article sends - tracks which articles were sent to which subscribers
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS article_sends (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subscriber_id INTEGER NOT NULL,
                article_id INTEGER NOT NULL,
                campaign_id INTEGER NOT NULL,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (subscriber_id) REFERENCES subscribers (id),
                FOREIGN KEY (article_id) REFERENCES articles (id),
                FOREIGN KEY (campaign_id) REFERENCES email_campaigns (id),
                UNIQUE(subscriber_id, article_id)
            )
        ''')

        # Admin settings - configuration and scheduling
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS admin_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Legacy users table - keep for migration purposes
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                state TEXT,
                frequency TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_sent TIMESTAMP
            )
        ''')

        # Initialize default admin settings
        default_settings = [
            ('email_schedule_day', '1'),  # Monday = 0, Tuesday = 1
            ('email_schedule_hour', '9'),
            ('email_schedule_minute', '0'),
            ('fallback_enabled', '1'),
            ('min_articles_per_category', '1')
        ]

        for key, value in default_settings:
            cursor.execute('''
                INSERT OR IGNORE INTO admin_settings (key, value) VALUES (?, ?)
            ''', (key, value))

        conn.commit()
        conn.close()

    def get_connection(self):
        """Get database connection"""
        return sqlite3.connect(self.db_path)

    # SUBSCRIBER MANAGEMENT
    def add_subscriber(self, email: str, issue_area: str, cadence: str = 'weekly') -> bool:
        """Add new subscriber or update existing one"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                INSERT OR REPLACE INTO subscribers 
                (email, issue_area, cadence, active, updated_at)
                VALUES (?, ?, ?, 1, ?)
            ''', (email, issue_area, cadence, datetime.now()))

            conn.commit()
            return True
        except Exception as e:
            print(f"Error adding subscriber: {e}")
            return False
        finally:
            conn.close()

    def get_subscriber_by_email(self, email: str) -> Optional[Dict]:
        """Get subscriber by email"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT id, email, issue_area, cadence, last_sent, active, created_at, updated_at
            FROM subscribers WHERE email = ?
        ''', (email,))

        row = cursor.fetchone()
        conn.close()

        if row:
            return {
                'id': row[0],
                'email': row[1],
                'issue_area': row[2],
                'cadence': row[3],
                'last_sent': row[4],
                'active': bool(row[5]),
                'created_at': row[6],
                'updated_at': row[7]
            }
        return None

    def get_all_active_subscribers(self) -> List[Dict]:
        """Get all active subscribers"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT id, email, issue_area, cadence, last_sent, created_at, updated_at
            FROM subscribers WHERE active = 1
            ORDER BY email
        ''')

        rows = cursor.fetchall()
        conn.close()

        return [{
            'id': row[0],
            'email': row[1],
            'issue_area': row[2],
            'cadence': row[3],
            'last_sent': row[4],
            'created_at': row[5],
            'updated_at': row[6]
        } for row in rows]

    def deactivate_subscriber(self, email: str) -> bool:
        """Deactivate subscriber (soft delete)"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                UPDATE subscribers SET active = 0, updated_at = ? WHERE email = ?
            ''', (datetime.now(), email))

            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            print(f"Error deactivating subscriber: {e}")
            return False
    def update_subscriber_last_sent(self, subscriber_id: int):
        """Update last_sent timestamp for subscriber"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                UPDATE subscribers SET last_sent = ?, updated_at = ? WHERE id = ?
            ''', (datetime.now().isoformat(), datetime.now().isoformat(), subscriber_id))
            conn.commit()
        except Exception as e:
            print(f"Error updating last_sent: {e}")
        finally:
            conn.close()

    def get_subscribers_due(self) -> List[Dict]:
        """Get all subscribers who are due for an email based on their cadence"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, email, issue_area, cadence, last_sent
            FROM subscribers WHERE active = 1
        ''')
        rows = cursor.fetchall()
        conn.close()
        
        due_subscribers = []
        now = datetime.now()
        
        for row in rows:
            sub_id, email, issue_area, cadence, last_sent_str = row
            
            if not last_sent_str:
                # Never sent before, so it's due
                due_subscribers.append({
                    'id': sub_id,
                    'email': email,
                    'issue_area': issue_area,
                    'cadence': cadence,
                    'last_sent': None
                })
                continue
                
            try:
                last_sent = datetime.fromisoformat(last_sent_str)
            except ValueError:
                # If there's a parsing error, assume due
                due_subscribers.append({
                    'id': sub_id,
                    'email': email,
                    'issue_area': issue_area,
                    'cadence': cadence,
                    'last_sent': None
                })
                continue
                
            is_due = False
            if cadence == 'daily':
                is_due = now - last_sent >= timedelta(days=1)
            elif cadence == 'weekly':
                is_due = now - last_sent >= timedelta(weeks=1)
            elif cadence == 'biweekly':
                is_due = now - last_sent >= timedelta(weeks=2)
            elif cadence == 'monthly':
                is_due = now - last_sent >= timedelta(days=30)
            else: # Default to weekly if invalid
                is_due = now - last_sent >= timedelta(weeks=1)
                
            if is_due:
                due_subscribers.append({
                    'id': sub_id,
                    'email': email,
                    'issue_area': issue_area,
                    'cadence': cadence,
                    'last_sent': last_sent
                })
                
        return due_subscribers

    # ARTICLE MANAGEMENT
    def add_article(self, title: str, url: str, outlet: str, issue_area: str) -> Optional[int]:
        """Add article to database, return article ID"""
        url_hash = hashlib.md5(url.encode()).hexdigest()

        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                INSERT OR IGNORE INTO articles 
                (url_hash, title, url, outlet, issue_area)
                VALUES (?, ?, ?, ?, ?)
            ''', (url_hash, title, url, outlet, issue_area))

            if cursor.rowcount > 0:
                article_id = cursor.lastrowid
            else:
                # Article already exists, get its ID
                cursor.execute('SELECT id FROM articles WHERE url_hash = ?', (url_hash,))
                article_id = cursor.fetchone()[0]

            conn.commit()
            return article_id
        except Exception as e:
            print(f"Error adding article: {e}")
            return None
        finally:
            conn.close()

    def get_fresh_articles_for_subscriber(self, subscriber_id: int, issue_areas: List[str]) -> Dict[str, List[Dict]]:
        """Get fresh articles for each issue area that haven't been sent to this subscriber"""
        conn = self.get_connection()
        cursor = conn.cursor()

        articles_by_category = {}

        for issue_area in issue_areas:
            cursor.execute('''
                SELECT a.id, a.title, a.url, a.outlet, a.issue_area, a.scraped_at
                FROM articles a
                LEFT JOIN article_sends s ON a.id = s.article_id AND s.subscriber_id = ?
                WHERE a.issue_area = ? 
                AND a.excluded = 0 
                AND s.id IS NULL
                ORDER BY a.scraped_at DESC
                LIMIT 10
            ''', (subscriber_id, issue_area))

            rows = cursor.fetchall()
            articles_by_category[issue_area] = [{
                'id': row[0],
                'title': row[1],
                'url': row[2],
                'outlet': row[3],
                'issue_area': row[4],
                'scraped_at': row[5]
            } for row in rows]

        conn.close()
        return articles_by_category

    def exclude_article(self, article_id: int, excluded: bool = True) -> bool:
        """Mark article as excluded from distribution"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                UPDATE articles SET excluded = ? WHERE id = ?
            ''', (excluded, article_id))

            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            print(f"Error updating article exclusion: {e}")
            return False
        finally:
            conn.close()

    # CAMPAIGN MANAGEMENT
    def create_campaign(self, campaign_type: str, scheduled_for: Optional[datetime] = None, notes: str = '') -> int:
        """Create new email campaign"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO email_campaigns (campaign_type, scheduled_for, notes)
            VALUES (?, ?, ?)
        ''', (campaign_type, scheduled_for, notes))

        campaign_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return campaign_id

    def record_article_send(self, subscriber_id: int, article_id: int, campaign_id: int):
        """Record that an article was sent to a subscriber"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                INSERT OR IGNORE INTO article_sends 
                (subscriber_id, article_id, campaign_id)
                VALUES (?, ?, ?)
            ''', (subscriber_id, article_id, campaign_id))

            conn.commit()
        except Exception as e:
            print(f"Error recording article send: {e}")
        finally:
            conn.close()

    def mark_campaign_sent(self, campaign_id: int, total_recipients: int, articles_sent: List[int]):
        """Mark campaign as sent"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            UPDATE email_campaigns 
            SET status = 'sent', sent_at = ?, total_recipients = ?, articles_sent = ?
            WHERE id = ?
        ''', (datetime.now(), total_recipients, json.dumps(articles_sent), campaign_id))

        conn.commit()
        conn.close()

    # ADMIN SETTINGS
    def get_setting(self, key: str, default: str = None) -> Optional[str]:
        """Get admin setting value"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT value FROM admin_settings WHERE key = ?', (key,))
        row = cursor.fetchone()
        conn.close()

        return row[0] if row else default

    def set_setting(self, key: str, value: str):
        """Set admin setting value"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            INSERT OR REPLACE INTO admin_settings (key, value, updated_at)
            VALUES (?, ?, ?)
        ''', (key, value, datetime.now()))

        conn.commit()
        conn.close()

    # STATISTICS AND REPORTING
    def get_subscriber_stats(self) -> Dict:
        """Get subscriber statistics"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT COUNT(*) FROM subscribers WHERE active = 1')
        active_count = cursor.fetchone()[0]

        cursor.execute('SELECT COUNT(*) FROM subscribers WHERE active = 0')
        inactive_count = cursor.fetchone()[0]

        cursor.execute('''
            SELECT issue_area_1 as issue FROM subscribers WHERE active = 1
            UNION ALL
            SELECT issue_area_2 as issue FROM subscribers WHERE active = 1
            UNION ALL
            SELECT issue_area_3 as issue FROM subscribers WHERE active = 1
        ''')

        issue_counts = {}
        for row in cursor.fetchall():
            issue = row[0]
            issue_counts[issue] = issue_counts.get(issue, 0) + 1

        conn.close()

        return {
            'active_subscribers': active_count,
            'inactive_subscribers': inactive_count,
            'total_subscribers': active_count + inactive_count,
            'popular_issues': sorted(issue_counts.items(), key=lambda x: x[1], reverse=True)
        }

    def get_recent_campaigns(self, limit: int = 10) -> List[Dict]:
        """Get recent email campaigns"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT id, campaign_type, status, scheduled_for, sent_at, total_recipients, notes
            FROM email_campaigns
            ORDER BY COALESCE(sent_at, scheduled_for, rowid) DESC
            LIMIT ?
        ''', (limit,))

        rows = cursor.fetchall()
        conn.close()

        return [{
            'id': row[0],
            'campaign_type': row[1],
            'status': row[2],
            'scheduled_for': row[3],
            'sent_at': row[4],
            'total_recipients': row[5],
            'notes': row[6]
        } for row in rows]