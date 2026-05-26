import os
import sqlite3
from datetime import datetime, timedelta
import pytest
from fastapi.testclient import TestClient

from src.models.database import DatabaseManager
from src.models.article import Subscriber, Article, ArticleSelector
from src.main import app


# Test database setup fixture
@pytest.fixture
def temp_db():
    db_path = "test_story_tracker.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    
    db = DatabaseManager(db_path)
    yield db
    
    # Cleanup after test runs
    if os.path.exists(db_path):
        os.remove(db_path)


def test_database_subscriber_management(temp_db):
    """Test creating and retrieving subscribers with customized cadence"""
    # 1. Add subscriber
    success = temp_db.add_subscriber("test@example.com", "Environmental Sustainability", "daily")
    assert success is True
    
    # 2. Retrieve subscriber
    sub = temp_db.get_subscriber_by_email("test@example.com")
    assert sub is not None
    assert sub['email'] == "test@example.com"
    assert sub['issue_area'] == "Environmental Sustainability"
    assert sub['cadence'] == "daily"
    assert sub['last_sent'] is None
    
    # 3. Retrieve all active
    active = temp_db.get_all_active_subscribers()
    assert len(active) == 1
    assert active[0]['email'] == "test@example.com"


def test_cadence_due_logic(temp_db):
    """Test the subscriber cadence due date calculations"""
    # Add a subscriber
    temp_db.add_subscriber("daily@example.com", "Health Care", "daily")
    temp_db.add_subscriber("weekly@example.com", "Education", "weekly")
    
    # Assert both are due initially (since last_sent is None)
    due = temp_db.get_subscribers_due()
    assert len(due) == 2
    
    # Get subscriber IDs
    sub_daily = temp_db.get_subscriber_by_email("daily@example.com")
    sub_weekly = temp_db.get_subscriber_by_email("weekly@example.com")
    
    # Update last_sent to exactly now (should make them NOT due)
    temp_db.update_subscriber_last_sent(sub_daily['id'])
    temp_db.update_subscriber_last_sent(sub_weekly['id'])
    
    due_after_update = temp_db.get_subscribers_due()
    assert len(due_after_update) == 0
    
    # Manually backdate daily subscriber's last_sent in DB to 2 days ago (should be due now)
    conn = temp_db.get_connection()
    cursor = conn.cursor()
    two_days_ago = (datetime.now() - timedelta(days=2)).isoformat()
    cursor.execute("UPDATE subscribers SET last_sent = ? WHERE email = ?", (two_days_ago, "daily@example.com"))
    conn.commit()
    conn.close()
    
    due_after_backdate = temp_db.get_subscribers_due()
    assert len(due_after_backdate) == 1
    assert due_after_backdate[0]['email'] == "daily@example.com"


def test_random_article_selector(temp_db):
    """Test ArticleSelector fetches and randomizes articles"""
    # Create subscriber
    temp_db.add_subscriber("user@example.com", "Environmental Sustainability", "weekly")
    sub_data = temp_db.get_subscriber_by_email("user@example.com")
    subscriber = Subscriber.from_dict(sub_data)
    
    # Add articles to database
    for i in range(10):
        temp_db.add_article(
            title=f"Sample Environmental Solutions Article {i}",
            url=f"https://example.com/story-{i}",
            outlet="Green News",
            issue_area="Environmental Sustainability"
        )
        
    selector = ArticleSelector(temp_db)
    
    # Select articles
    selected = selector.select_articles_for_subscriber(subscriber, articles_per_category=3)
    assert "Environmental Sustainability" in selected
    assert len(selected["Environmental Sustainability"]) == 3
    
    # Verify they are Article dataclass objects
    for article in selected["Environmental Sustainability"]:
        assert isinstance(article, Article)
        assert article.issue_area == "Environmental Sustainability"


def test_fastapi_subscription_endpoint(temp_db):
    """Test the POST /api/subscribe subscription endpoint"""
    # Override database path in main.py database object for testing
    from src.main import db as main_db
    test_db_path = "api_test_story_tracker.db"
    
    if os.path.exists(test_db_path):
        os.remove(test_db_path)
        
    main_db.db_path = test_db_path
    main_db.init_database()
    
    client = TestClient(app)
    
    # 1. Test health check
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    
    # 2. Test dynamic issue areas list retrieval
    response = client.get("/api/issues")
    assert response.status_code == 200
    assert "Environmental Sustainability" in response.json()
    
    # 3. Test successful signup POST request
    payload = {
        "email": "api_subscriber@example.com",
        "issue_area": "Environmental Sustainability",
        "cadence": "weekly"
    }
    
    response = client.post("/api/subscribe", json=payload)
    assert response.status_code == 201
    assert response.json()["success"] is True
    
    # 4. Test invalid email format handling
    bad_payload = {
        "email": "invalid-email-address",
        "issue_area": "Health Care",
        "cadence": "daily"
    }
    response = client.post("/api/subscribe", json=bad_payload)
    assert response.status_code == 422 # Unprocessable Entity
    
    # Cleanup API test DB
    if os.path.exists(test_db_path):
        os.remove(test_db_path)
