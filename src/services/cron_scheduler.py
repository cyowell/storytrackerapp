import os
import sys
from pathlib import Path
from datetime import datetime

# Add project root to python path to allow absolute imports
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))

# Zero-dependency .env loader for secure local configuration
env_path = project_root / '.env'
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, val = line.split('=', 1)
                os.environ[key.strip()] = val.strip().strip('"').strip("'")

from src.models.database import DatabaseManager
from src.models.article import Subscriber, Article
from src.services.scraper import SolutionsStoryScraper
from src.services.email_service import EmailService


def run_newsletter_distribution():
    """Checks for due subscribers, scrapes fresh articles, and distributes emails via Resend"""
    print(f"\n--- Starting Newsletter Distribution Run: {datetime.now()} ---")
    
    # Initialize services
    db_manager = DatabaseManager()
    scraper = SolutionsStoryScraper(db_manager)
    email_service = EmailService(db_manager)
    
    # Get all subscribers due for their email
    due_subscribers = db_manager.get_subscribers_due()
    print(f"Found {len(due_subscribers)} subscribers due for their digest.")
    
    if not due_subscribers:
        print("No newsletters to distribute at this time.")
        return
        
    # Keep track of which categories we have already scraped in this run to avoid redundant requests
    scraped_categories = set()
    
    # Track campaign statistics
    successful_sends = 0
    failed_sends = 0
    
    # Create an email campaign in the database
    campaign_id = db_manager.create_campaign(
        campaign_type='scheduled',
        notes=f"Cron automated digest sent to {len(due_subscribers)} prospective lists"
    )
    
    for sub_data in due_subscribers:
        email = sub_data['email']
        issue_area = sub_data['issue_area']
        subscriber_id = sub_data['id']
        
        print(f"\nProcessing subscription list: {email} for issue area: '{issue_area}'")
        
        # 1. Scrape latest stories for this category first if we haven't already in this run
        if issue_area not in scraped_categories:
            print(f"Scraping latest stories for '{issue_area}' to populate the pool...")
            try:
                # Scrape 15 stories from the new results portal to make sure we have a fresh random pool
                scraper.scrape_articles_for_issue(issue_area, limit=15)
                scraped_categories.add(issue_area)
            except Exception as e:
                print(f"Error scraping category {issue_area}: {e}")
                
        # 2. Get subscriber model object
        subscriber = Subscriber(
            id=subscriber_id,
            email=email,
            issue_area=issue_area,
            cadence=sub_data['cadence'],
            last_sent=sub_data['last_sent']
        )
        
        # 3. Generate customized HTML digest pulling random fresh articles
        try:
            # We pull 3 random articles for this digest
            html_content = email_service.generate_newsletter_for_subscriber(
                subscriber=subscriber,
                campaign_id=campaign_id,
                articles_per_category=3
            )
            
            if html_content:
                # 4. Deliver live using Resend API
                print(f"Delivering customized email digest to {email}...")
                sent = email_service.send_email_via_resend(
                    to_email=email,
                    subject=f"Custom Solutions Stories: {issue_area}",
                    html_content=html_content
                )
                
                if sent:
                    # Save backup file
                    email_service._save_email_to_file(email, html_content, campaign_id)
                    # Update database last_sent
                    db_manager.update_subscriber_last_sent(subscriber_id)
                    successful_sends += 1
                    print(f"✓ Newsletter successfully dispatched and recorded for {email}")
                else:
                    failed_sends += 1
                    print(f"✗ Delivery failed via Resend for {email}")
            else:
                failed_sends += 1
                print(f"✗ Could not select new articles or generate digest for {email}")
                
        except Exception as e:
            failed_sends += 1
            print(f"✗ Error processing digest for {email}: {e}")
            
    # Mark campaign as completed
    db_manager.mark_campaign_sent(campaign_id, successful_sends, [])
    print(f"\n--- Distribution Run Complete. Dispatched: {successful_sends}, Failed: {failed_sends} ---")


if __name__ == "__main__":
    # If a Resend API key is not configured, warn the user
    if not os.environ.get("RESEND_API_KEY"):
        print("[Warning] RESEND_API_KEY environment variable is not configured.")
        print("Emails will generate locally in 'emails_output/', but live Resend transmission will be skipped.")
        
    run_newsletter_distribution()
