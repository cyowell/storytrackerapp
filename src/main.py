import os
import sys
import requests
from pathlib import Path
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr

# Add project root to python path to allow absolute imports
project_root = Path(__file__).parent.parent
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

app = FastAPI(
    title="Story Tracker Newsletter API Backend",
    description="Secure backend to collect subscription preferences and provide solutions journalism issue areas.",
    version="2.0.0"
)

# Configure CORS so your static site on GitHub Pages can securely communicate with this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins. For production, you can lock this to your GitHub Pages URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize database
db = DatabaseManager()

# Pydantic schema for subscription input validation
class SubscriptionRequest(BaseModel):
    email: EmailStr
    issue_area: str
    cadence: str = "weekly"  # "daily", "weekly", "biweekly", "monthly"
    preferred_day: str = "Monday"
    preferred_hour: int = 9


# Available issue areas and subcategories tree matching the portal structure
ISSUE_AREAS_TREE = {
    "Agriculture & Food Systems": [
        "Food security", "Community food systems", "Food sovereignty", "Food waste", "Sustainable agriculture"
    ],
    "Arts": [
        "Artist's services", "Arts administration and services", "Museums", "Performing arts", "Dance"
    ],
    "Business & Industry": [
        "Business promotion", "Construction and real estate", "Corporate social responsibility", "Entrepreneurship", "Social entrepreneurship"
    ],
    "COVID-19 and SARS Coronavirus 2": [
        "Care and Compassion", "Creating Companionship", "Electronic Empathy", "Making Grieving Accessible", "Making It Light"
    ],
    "Community Development": [
        "Bicycling and pedestrian-oriented development", "Community beautification", "Gardening and landscaping", "Community improvement", "Community organizing"
    ],
    "Criminal Justice & Law": [
        "Abuse prevention", "Bullying", "Child abuse", "Domestic, intimate partner and gender-based violence", "Elder abuse"
    ],
    "Culture": [
        "Building cultural awareness", "Preserving indigenous cultural knowledge", "Folk, ethnic and indigenous arts", "History", "Language acquisition and linguistics"
    ],
    "Democracy": [
        "Civic participation", "Civics for youth", "Civics education", "Elections", "Voter education and registration"
    ],
    "Economic Development & Mobility": [
        "Digital divide", "Financial services", "Banking, credit unions and investment services", "Community development finance", "Insurance and financial counseling"
    ],
    "Education": [
        "Adult education", "Arts education", "Colleges and universities", "Community colleges", "Early childhood education"
    ],
    "Environmental Sustainability": [
        "Air quality and air pollution", "Animal welfare", "Animal companionship", "Climate change", "Climate change adaptation"
    ],
    "Government Operations": [
        "Democracy and civil society development", "Government regulation", "Government surveillance systems", "Immigration and naturalization", "International development"
    ],
    "Health Care": [
        "Caregivers", "Disease treatment and management", "Emergency medical services", "Health care management and administration", "Health equity"
    ],
    "Human & Social Services": [
        "Adult peer mentoring", "Adult social services", "Caregiver and respite services", "Child care and early childhood development", "Child welfare"
    ],
    "Human Rights": [
        "Diversity and intergroup relations", "Economic justice", "Ending slavery and human trafficking", "Environmental rights and justice", "Environmental racism"
    ],
    "Mental Health Care": [
        "Addiction treatment services", "Alcohol use disorders", "Opioids", "Substance abuse prevention and treatment programs", "Crisis support services"
    ],
    "North Carolina Hurricane Helene climate disaster": [
        "NC Helene Communications & Information Management", "NC Helene Coping and Adapting", "NC Helene Distribution of Immediate Services"
    ],
    "Philanthropy": [
        "Foundations", "Fundraising", "Nonprofits", "Venture philanthropy", "Volunteer opportunities"
    ],
    "Public Information & Communications": [
        "Applications software", "Data analysis and database management software", "Data and information security", "Geographic information systems", "Interactive games and simulation software"
    ],
    "Public Safety & Disaster Management": [
        "Accessibility and universal design", "Consumer protection", "Drug safety", "Food safety", "Disasters and emergency management"
    ],
    "Religion": [
        "Buddhism", "Christianity", "Hinduism", "Interfaith", "Islam"
    ],
    "Science & Technology": [
        "Assistive technology and software", "Biology", "Genetics and stem cell therapy", "Computer science", "Algorithms, artificial intelligence and machine learning"
    ],
    "Social Sciences & Humanities": [
        "Economics", "Interdisciplinary studies", "Asian American and Pacific Islander studies", "Black and African American Studies", "Gender studies"
    ],
    "Sports & Recreation": [
        "Community recreation", "Parks", "Sports", "Adaptive sports for people with disabilities", "School athletics"
    ]
}


@app.get("/health", status_code=status.HTTP_200_OK)
def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "Story Tracker API Backend"}


@app.get("/api/issues", response_model=Dict[str, List[str]])
def get_issue_areas():
    """Returns all 24 categorized issue areas and subcategories"""
    return ISSUE_AREAS_TREE


def add_contact_to_resend_sojo(email: str) -> bool:
    """Add a new subscriber contact to the Resend 'Sojo' segment"""
    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        print("[Warning] RESEND_API_KEY not found in backend. Skipping live Resend segment registration.")
        return False
        
    try:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "email": email,
            "unsubscribed": False,
            "segments": [
                {
                    "id": "b37b1fee-7f7b-4ab0-908d-fd4441efc363"
                }
            ]
        }
        response = requests.post("https://api.resend.com/contacts", json=payload, headers=headers, timeout=10)
        if response.status_code in [200, 201]:
            print(f"✓ Resend successfully added contact {email} to segment 'Sojo' (b37b1fee-7f7b-4ab0-908d-fd4441efc363)")
            return True
        else:
            print(f"✗ Resend API segment registration error: {response.status_code} {response.text}")
            return False
    except Exception as e:
        print(f"✗ Exception in Resend segment registration: {e}")
        return False


@app.post("/api/subscribe", status_code=status.HTTP_201_CREATED)
def subscribe_user(payload: SubscriptionRequest):
    """Exposes endpoint for signup form submissions"""
    # 1. Validate cadence
    valid_cadences = ["daily", "weekly", "biweekly", "monthly"]
    if payload.cadence.lower() not in valid_cadences:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid cadence. Must be one of {valid_cadences}"
        )

    # 2. Store in sqlite database
    success = db.add_subscriber(
        email=payload.email,
        issue_area=payload.issue_area,
        cadence=payload.cadence.lower(),
        preferred_day=payload.preferred_day,
        preferred_hour=payload.preferred_hour
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record preference selection in the database."
        )

    # 3. Synchronize contact directly with Resend "Sojo" segment list
    add_contact_to_resend_sojo(payload.email)

    return {
        "success": True,
        "message": f"Successfully registered preference subscription list for {payload.email}",
        "data": {
            "email": payload.email,
            "issue_area": payload.issue_area,
            "cadence": payload.cadence,
            "preferred_day": payload.preferred_day,
            "preferred_hour": payload.preferred_hour
        }
    }


if __name__ == "__main__":
    import uvicorn
    # Start uvicorn server locally on port 8000
    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=True)