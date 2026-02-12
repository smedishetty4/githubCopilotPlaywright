import pytest
from fastapi.testclient import TestClient
import sys
from pathlib import Path

# Add src directory to path so we can import app
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from app import app


@pytest.fixture
def client():
    """Create a test client for the FastAPI app"""
    return TestClient(app)


@pytest.fixture
def reset_activities():
    """Reset activities to known state before each test"""
    # Store original state
    from app import activities
    original_state = {
        name: {
            "description": details["description"],
            "schedule": details["schedule"],
            "max_participants": details["max_participants"],
            "participants": details["participants"].copy()
        }
        for name, details in activities.items()
    }
    yield
    # Restore original state after test
    activities.clear()
    for name, details in original_state.items():
        activities[name] = details


class TestActivitiesEndpoint:
    """Tests for GET /activities endpoint"""

    def test_get_activities(self, client, reset_activities):
        """Test retrieving all activities"""
        response = client.get("/activities")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, dict)
        assert len(data) > 0
        
        # Check that all activities have required fields
        for activity_name, activity_details in data.items():
            assert "description" in activity_details
            assert "schedule" in activity_details
            assert "max_participants" in activity_details
            assert "participants" in activity_details
            assert isinstance(activity_details["participants"], list)

    def test_get_activities_tennis_club(self, client, reset_activities):
        """Test that Tennis Club activity exists in the list"""
        response = client.get("/activities")
        data = response.json()
        
        assert "Tennis Club" in data
        assert data["Tennis Club"]["description"] == "Learn tennis skills and participate in friendly matches"
        assert data["Tennis Club"]["max_participants"] == 16


class TestSignupEndpoint:
    """Tests for POST /activities/{activity_name}/signup endpoint"""

    def test_signup_success(self, client, reset_activities):
        """Test successful signup for an activity"""
        response = client.post(
            "/activities/Chess Club/signup?email=student@mergington.edu"
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "message" in data
        assert "student@mergington.edu" in data["message"]
        assert "Chess Club" in data["message"]

    def test_signup_duplicate_student(self, client, reset_activities):
        """Test that a student cannot sign up twice for the same activity"""
        # Sign up a student
        response1 = client.post(
            "/activities/Tennis Club/signup?email=duplicate@mergington.edu"
        )
        assert response1.status_code == 200
        
        # Try to sign up the same student again
        response2 = client.post(
            "/activities/Tennis Club/signup?email=duplicate@mergington.edu"
        )
        assert response2.status_code == 400
        assert "already signed up" in response2.json()["detail"]

    def test_signup_nonexistent_activity(self, client, reset_activities):
        """Test signup for a non-existent activity"""
        response = client.post(
            "/activities/Nonexistent Club/signup?email=student@mergington.edu"
        )
        assert response.status_code == 404
        assert "Activity not found" in response.json()["detail"]

    def test_signup_at_capacity(self, client, reset_activities):
        """Test signup when activity is at capacity"""
        from app import activities
        
        # Fill up Gym Class (30 capacity)
        activity = activities["Gym Class"]
        original_participants = activity["participants"].copy()
        
        # Add participants to reach capacity
        for i in range(activity["max_participants"] - len(activity["participants"])):
            activity["participants"].append(f"filler{i}@mergington.edu")
        
        # Try to sign up when at capacity
        response = client.post(
            "/activities/Gym Class/signup?email=newstudent@mergington.edu"
        )
        assert response.status_code == 400
        assert "at capacity" in response.json()["detail"]
        
        # Restore original participants
        activity["participants"] = original_participants

    def test_signup_updates_participant_list(self, client, reset_activities):
        """Test that signup updates the participant list in activities"""
        from app import activities
        
        initial_count = len(activities["Tennis Club"]["participants"])
        
        response = client.post(
            "/activities/Tennis Club/signup?email=newparticipant@mergington.edu"
        )
        assert response.status_code == 200
        
        updated_count = len(activities["Tennis Club"]["participants"])
        assert updated_count == initial_count + 1
        assert "newparticipant@mergington.edu" in activities["Tennis Club"]["participants"]


class TestUnregisterEndpoint:
    """Tests for DELETE /activities/{activity_name}/unregister endpoint"""

    def test_unregister_success(self, client, reset_activities):
        """Test successful unregistration from an activity"""
        from app import activities
        
        # First signup
        client.post("/activities/Art Studio/signup?email=testuser@mergington.edu")
        
        # Then unregister
        response = client.delete(
            "/activities/Art Studio/unregister?email=testuser@mergington.edu"
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "message" in data
        assert "testuser@mergington.edu" in data["message"]
        assert "Unregistered" in data["message"]
        assert "testuser@mergington.edu" not in activities["Art Studio"]["participants"]

    def test_unregister_not_registered(self, client, reset_activities):
        """Test unregistering a student who was never registered"""
        response = client.delete(
            "/activities/Music Ensemble/unregister?email=notregistered@mergington.edu"
        )
        assert response.status_code == 400
        assert "not registered" in response.json()["detail"]

    def test_unregister_nonexistent_activity(self, client, reset_activities):
        """Test unregistering from a non-existent activity"""
        response = client.delete(
            "/activities/Nonexistent Club/unregister?email=student@mergington.edu"
        )
        assert response.status_code == 404
        assert "Activity not found" in response.json()["detail"]

    def test_unregister_existing_participant(self, client, reset_activities):
        """Test unregistering an existing participant from an activity"""
        from app import activities
        
        # Alex is already registered for Tennis Club
        initial_participants = activities["Tennis Club"]["participants"].copy()
        assert "alex@mergington.edu" in initial_participants
        
        response = client.delete(
            "/activities/Tennis Club/unregister?email=alex@mergington.edu"
        )
        assert response.status_code == 200
        assert "alex@mergington.edu" not in activities["Tennis Club"]["participants"]


class TestIntegrationFlow:
    """Integration tests for complete user flows"""

    def test_full_signup_and_unregister_flow(self, client, reset_activities):
        """Test complete flow: signup, verify, unregister, verify"""
        from app import activities
        
        email = "integration_test@mergington.edu"
        activity_name = "Debate Club"
        
        # Initial state
        assert email not in activities[activity_name]["participants"]
        
        # Signup
        signup_response = client.post(
            f"/activities/{activity_name}/signup?email={email}"
        )
        assert signup_response.status_code == 200
        assert email in activities[activity_name]["participants"]
        
        # Verify in activities list
        activities_response = client.get("/activities")
        assert email in activities_response.json()[activity_name]["participants"]
        
        # Unregister
        unregister_response = client.delete(
            f"/activities/{activity_name}/unregister?email={email}"
        )
        assert unregister_response.status_code == 200
        assert email not in activities[activity_name]["participants"]
        
        # Verify removal
        final_response = client.get("/activities")
        assert email not in final_response.json()[activity_name]["participants"]

    def test_multiple_participants_management(self, client, reset_activities):
        """Test managing multiple participants"""
        from app import activities
        
        activity_name = "Programming Class"
        users = ["user1@test.edu", "user2@test.edu", "user3@test.edu"]
        
        # Signup all users
        for user in users:
            response = client.post(
                f"/activities/{activity_name}/signup?email={user}"
            )
            assert response.status_code == 200
        
        # Verify all are registered
        activities_response = client.get("/activities")
        participants = activities_response.json()[activity_name]["participants"]
        for user in users:
            assert user in participants
        
        # Unregister middle user
        client.delete(
            f"/activities/{activity_name}/unregister?email={users[1]}"
        )
        
        # Verify remaining users are still there
        final_response = client.get("/activities")
        final_participants = final_response.json()[activity_name]["participants"]
        assert users[0] in final_participants
        assert users[1] not in final_participants
        assert users[2] in final_participants
