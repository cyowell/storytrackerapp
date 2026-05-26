import os
import requests
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path

from src.models.database import DatabaseManager
from src.models.article import Article, Subscriber, ArticleSelector


class EmailService:
    """Handles email generation and delivery for the Story Tracker app using Resend"""

    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self.article_selector = ArticleSelector(db_manager)
        self.output_dir = Path("emails_output")
        self.output_dir.mkdir(exist_ok=True)
        self.resend_api_key = os.environ.get("RESEND_API_KEY")
        self.from_address = os.environ.get("EMAIL_FROM_ADDRESS", "onboarding@resend.dev")

    def send_email_via_resend(self, to_email: str, subject: str, html_content: str) -> bool:
        """Sends an HTML email to a recipient using Resend API"""
        if not self.resend_api_key:
            print("[Warning] RESEND_API_KEY not found. Skipping live email delivery.")
            return False

        try:
            headers = {
                "Authorization": f"Bearer {self.resend_api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "from": self.from_address,
                "to": [to_email],
                "subject": subject,
                "html": html_content
            }
            
            response = requests.post("https://api.resend.com/emails", json=payload, headers=headers, timeout=10)
            
            if response.status_code in [200, 201]:
                print(f"✓ Resend successfully delivered email to {to_email}")
                return True
            else:
                print(f"✗ Resend API returned error status {response.status_code}: {response.text}")
                return False
        except Exception as e:
            print(f"✗ Exception occurred while calling Resend API: {e}")
            return False

    def generate_newsletter_for_subscriber(self, subscriber: Subscriber, campaign_id: int, articles_per_category: int = 3) -> Optional[str]:
        """
        Generate newsletter content for a single subscriber
        Returns the email content as HTML string
        """
        # Select articles for subscriber
        selected_articles = self.article_selector.select_articles_for_subscriber(subscriber, articles_per_category)

        if not any(selected_articles.values()):
            print(f"No articles found for subscriber {subscriber.email}")
            return None

        # Record article sends in database
        for issue_area, articles in selected_articles.items():
            for article in articles:
                if article.id:
                    self.db.record_article_send(subscriber.id, article.id, campaign_id)

        # Generate HTML email content
        html_content = self._generate_html_email(subscriber, selected_articles)

        return html_content

    def send_newsletter_campaign(self, campaign_type: str = 'scheduled',
                                 manual_articles: Optional[List[int]] = None) -> Dict:
        """
        Send newsletter campaign to all active subscribers
        Returns summary of the campaign
        """
        # Get all active subscribers
        subscribers_data = self.db.get_all_active_subscribers()
        subscribers = [Subscriber.from_dict(data) for data in subscribers_data]

        if not subscribers:
            return {"success": False, "message": "No active subscribers found"}

        # Create campaign record
        campaign_id = self.db.create_campaign(
            campaign_type=campaign_type,
            notes=f"Campaign sent to {len(subscribers)} subscribers"
        )

        successful_sends = 0
        failed_sends = 0
        all_articles_sent = set()

        print(f"Starting campaign {campaign_id} for {len(subscribers)} subscribers...")

        for subscriber in subscribers:
            try:
                if manual_articles:
                    # Manual campaign with specific articles
                    html_content = self._generate_manual_campaign_email(
                        subscriber, manual_articles, campaign_id
                    )
                else:
                    # Regular personalized campaign
                    html_content = self.generate_newsletter_for_subscriber(subscriber, campaign_id)

                if html_content:
                    # Save email to local file backup
                    self._save_email_to_file(subscriber.email, html_content, campaign_id)
                    
                    # Deliver live via Resend
                    sent = self.send_email_via_resend(
                        to_email=subscriber.email,
                        subject=f"Your Customized Solutions Stories Digest - {subscriber.issue_area}",
                        html_content=html_content
                    )
                    
                    if sent:
                        successful_sends += 1
                        # Update the subscriber's last sent timestamp
                        self.db.update_subscriber_last_sent(subscriber.id)
                    else:
                        failed_sends += 1
                else:
                    failed_sends += 1
                    print(f"✗ Failed to generate email content for {subscriber.email}")

            except Exception as e:
                failed_sends += 1
                print(f"✗ Error generating email for {subscriber.email}: {e}")

        # Mark campaign as sent
        if successful_sends > 0:
            self.db.mark_campaign_sent(campaign_id, successful_sends, list(all_articles_sent))

        # Generate campaign summary
        summary = {
            "success": True,
            "campaign_id": campaign_id,
            "total_subscribers": len(subscribers),
            "successful_sends": successful_sends,
            "failed_sends": failed_sends,
            "timestamp": datetime.now().isoformat()
        }

        # Save campaign summary
        self._save_campaign_summary(campaign_id, summary)

        print(f"\nCampaign {campaign_id} completed:")
        print(f"✓ Successful sends: {successful_sends}")
        print(f"✗ Failed sends: {failed_sends}")

        return summary

    def _generate_html_email(self, subscriber: Subscriber,
                             selected_articles: Dict[str, List[Article]]) -> str:
        """Generate a gorgeous premium HTML email content for subscriber"""

        total_articles = sum(len(articles) for articles in selected_articles.values())

        html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Your Solutions Stories Digest</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #1a1a24;
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f6f8fa;
        }}
        .email-container {{
            background-color: #ffffff;
            padding: 40px 30px;
            border-radius: 16px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.05);
            border: 1px solid #eef2f6;
        }}
        .header {{
            text-align: center;
            margin-bottom: 40px;
            border-bottom: 2px solid #eef2f6;
            padding-bottom: 24px;
        }}
        .logo {{
            font-size: 24px;
            font-weight: 800;
            color: #0b84ff;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 8px;
        }}
        .header h1 {{
            color: #1e293b;
            margin: 0 0 8px 0;
            font-size: 22px;
            font-weight: 700;
        }}
        .header .date {{
            color: #64748b;
            font-size: 14px;
            margin-top: 5px;
        }}
        .intro {{
            font-size: 16px;
            color: #475569;
            margin-bottom: 30px;
        }}
        .issue-section {{
            margin-bottom: 35px;
        }}
        .issue-title {{
            color: #0f172a;
            font-size: 18px;
            font-weight: 700;
            margin-bottom: 20px;
            border-bottom: 2px solid #0b84ff;
            padding-bottom: 6px;
            display: inline-block;
        }}
        .article {{
            margin-bottom: 28px;
            padding: 24px;
            background-color: #f8fafc;
            border-radius: 12px;
            border: 1px solid #f1f5f9;
            transition: transform 0.2s;
        }}
        .article-title {{
            font-size: 18px;
            font-weight: 700;
            margin-bottom: 8px;
            line-height: 1.4;
        }}
        .article-title a {{
            color: #1e293b;
            text-decoration: none;
        }}
        .article-title a:hover {{
            color: #0b84ff;
        }}
        .article-meta {{
            font-size: 13px;
            color: #64748b;
            margin-top: 12px;
            font-weight: 500;
        }}
        .read-btn {{
            display: inline-block;
            margin-top: 14px;
            padding: 8px 16px;
            background-color: #0b84ff;
            color: #ffffff !important;
            text-decoration: none;
            font-weight: 600;
            font-size: 14px;
            border-radius: 6px;
        }}
        .read-btn:hover {{
            background-color: #0066cc;
        }}
        .fallback-notice {{
            background-color: #fffbeb;
            border: 1px solid #fef3c7;
            color: #b45309;
            padding: 12px 16px;
            border-radius: 8px;
            font-size: 14px;
            margin-bottom: 20px;
            font-weight: 500;
        }}
        .footer {{
            margin-top: 50px;
            padding-top: 24px;
            border-top: 1px solid #eef2f6;
            text-align: center;
            font-size: 13px;
            color: #94a3b8;
            line-height: 1.8;
        }}
        .footer a {{
            color: #0b84ff;
            text-decoration: none;
            font-weight: 600;
        }}
    </style>
</head>
<body>
    <div class="email-container">
        <div class="header">
            <div class="logo">Story Tracker</div>
            <h1>Your Customized Solutions Stories</h1>
            <div class="date">{datetime.now().strftime('%B %d, %Y')}</div>
        </div>

        <p class="intro">Here is your automated Solutions Journalism digest on <strong>{subscriber.issue_area}</strong>, delivered on your <strong>{subscriber.cadence}</strong> schedule.</p>
"""

        # Add each issue section
        for issue_area in subscriber.issue_areas:
            articles = selected_articles.get(issue_area, [])

            html_content += f'<div class="issue-section">\n'
            html_content += f'<div class="issue-title">{issue_area}</div>\n'

            # Check if fallback was used
            if self.article_selector.was_fallback_used(issue_area):
                html_content += '''
                <div class="fallback-notice">
                    Note: We included some articles from related categories to ensure you have fresh content in this digest.
                </div>
                '''

            if articles:
                for article in articles:
                    html_content += f'''
                <div class="article">
                    <div class="article-title">
                        <a href="{article.url}" target="_blank">{article.title}</a>
                    </div>
                    <div class="article-meta">
                        Source: <strong>{article.outlet or 'Solutions Journalism'}</strong> • Category: {article.issue_area}
                    </div>
                    <a href="{article.url}" class="read-btn" target="_blank">Read Story</a>
                </div>
                '''
            else:
                html_content += '''
                <div class="article">
                    <div class="article-meta" style="font-style: italic;">
                        No new articles available in this category for this period. We'll check again soon!
                    </div>
                </div>
                '''

            html_content += '</div>\n'

        # Add footer
        html_content += f"""
        <div class="footer">
            <p>Sent with care to <strong>{subscriber.email}</strong></p>
            <p>You can update your customized issue topic or change your schedule cadence at any time.</p>
            <p><a href="#">Manage Preferences</a> • <a href="#">Unsubscribe</a></p>
        </div>
    </div>
</body>
</html>
"""

        return html_content

    def _generate_manual_campaign_email(self, subscriber: Subscriber,
                                        article_ids: List[int], campaign_id: int) -> str:
        """Generate email for manual campaign with specific articles"""
        articles = []
        conn = self.db.get_connection()
        cursor = conn.cursor()

        for article_id in article_ids:
            cursor.execute('''
                SELECT id, title, url, outlet, issue_area, scraped_at
                FROM articles WHERE id = ?
            ''', (article_id,))

            row = cursor.fetchone()
            if row:
                article = Article(
                    id=row[0],
                    title=row[1],
                    url=row[2],
                    outlet=row[3],
                    issue_area=row[4],
                    scraped_at=datetime.fromisoformat(row[5]) if row[5] else None
                )
                articles.append(article)
                self.db.record_article_send(subscriber.id, article_id, campaign_id)

        conn.close()

        if not articles:
            return None

        # Build custom manual HTML
        html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Curated Solutions Stories Collection</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            color: #1a1a24;
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f6f8fa;
        }}
        .email-container {{
            background-color: #ffffff;
            padding: 40px 30px;
            border-radius: 16px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.05);
            border: 1px solid #eef2f6;
        }}
        .header {{
            text-align: center;
            margin-bottom: 40px;
            border-bottom: 2px solid #eef2f6;
            padding-bottom: 24px;
        }}
        .logo {{
            font-size: 24px;
            font-weight: 800;
            color: #0b84ff;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 8px;
        }}
        .header h1 {{
            color: #1e293b;
            margin: 0 0 8px 0;
            font-size: 22px;
            font-weight: 700;
        }}
        .article {{
            margin-bottom: 28px;
            padding: 24px;
            background-color: #f8fafc;
            border-radius: 12px;
            border: 1px solid #f1f5f9;
        }}
        .article-title {{
            font-size: 18px;
            font-weight: 700;
            margin-bottom: 8px;
        }}
        .article-title a {{
            color: #1e293b;
            text-decoration: none;
        }}
        .article-meta {{
            font-size: 13px;
            color: #64748b;
            margin-top: 12px;
        }}
        .read-btn {{
            display: inline-block;
            margin-top: 14px;
            padding: 8px 16px;
            background-color: #0b84ff;
            color: #ffffff !important;
            text-decoration: none;
            font-weight: 600;
            font-size: 14px;
            border-radius: 6px;
        }}
        .footer {{
            margin-top: 50px;
            padding-top: 24px;
            border-top: 1px solid #eef2f6;
            text-align: center;
            font-size: 13px;
            color: #94a3b8;
        }}
        .footer a {{
            color: #0b84ff;
            text-decoration: none;
        }}
    </style>
</head>
<body>
    <div class="email-container">
        <div class="header">
            <div class="logo">Story Tracker</div>
            <h1>Curated Solutions Stories Collection</h1>
            <div class="date">{datetime.now().strftime('%B %d, %Y')}</div>
        </div>

        <p>Hello! We have curated a special collection of {len(articles)} solutions stories that we think you'll find inspiring.</p>
"""

        for article in articles:
            html_content += f'''
            <div class="article">
                <div class="article-title">
                    <a href="{article.url}" target="_blank">{article.title}</a>
                </div>
                <div class="article-meta">
                    Source: <strong>{article.outlet or 'Solutions Journalism'}</strong> • Category: {article.issue_area}
                </div>
                <a href="{article.url}" class="read-btn" target="_blank">Read Story</a>
            </div>
            '''

        html_content += f"""
        <div class="footer">
            <p>Sent with care to <strong>{subscriber.email}</strong></p>
            <p><a href="#">Manage Preferences</a> • <a href="#">Unsubscribe</a></p>
        </div>
    </div>
</body>
</html>
"""
        return html_content

    def _save_email_to_file(self, email: str, html_content: str, campaign_id: int):
        """Save generated email to file as a backup"""
        safe_email = email.replace('@', '_at_').replace('.', '_')
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"campaign_{campaign_id}_{safe_email}_{timestamp}.html"

        filepath = self.output_dir / filename
        filepath.write_text(html_content, encoding='utf-8')
        print(f"Backup email saved to: {filepath}")

    def _save_campaign_summary(self, campaign_id: int, summary: Dict):
        """Save campaign summary to file"""
        import json
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"campaign_summary_{campaign_id}_{timestamp}.json"

        filepath = self.output_dir / filename
        filepath.write_text(json.dumps(summary, indent=2), encoding='utf-8')

    def preview_newsletter_for_subscriber(self, subscriber_email: str) -> Optional[str]:
        """Generate preview of newsletter for a subscriber without recording sends"""
        subscriber_data = self.db.get_subscriber_by_email(subscriber_email)
        if not subscriber_data:
            return None

        subscriber = Subscriber.from_dict(subscriber_data)
        selected_articles = self.article_selector.select_articles_for_subscriber(subscriber)
        html_content = self._generate_html_email(subscriber, selected_articles)
        return html_content