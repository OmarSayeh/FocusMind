import os
import subprocess
import json
from pathlib import Path
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from openai import OpenAI
from pydantic import BaseModel
import random

# Import the focus scoring system
from FocusScore import generate_focus_chart_base64, generate_session_stats

# Import the face tracking system
from face_focus_tracker import FaceFocusTracker

# Global attention score variable (shared state)
attention_score = 100

# Global focus score tracking for the current session
focus_score_history = []

# Agent mode state
agent_mode = "goggins"

# Store the most recent focus metrics from the tracker for health interventions
last_focus_metrics = None  # type: Optional["FocusMetrics"]

# Global face tracking variables
face_tracker = None
tracking_active = False

# Load environment variables from .env file
load_dotenv()

app = FastAPI(title="FocusMind API", description="Motivational Study Coach API")

# Create audio directory if it doesn't exist
audio_dir = Path("audio_files")
audio_dir.mkdir(exist_ok=True)

# Mount static files for audio serving
app.mount("/audio", StaticFiles(directory="audio_files"), name="audio")

# Add CORS middleware to allow React frontend to connect
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001", "http://localhost:3002", "http://localhost:3003", "http://localhost:3004", "http://localhost:3005", "http://localhost:3006", "http://localhost:3007", "http://localhost:3008"],  # React dev server on multiple ports
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize OpenAI client
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("OPENAI_API_KEY environment variable is required")

client = OpenAI(api_key=api_key)

class MotivationResponse(BaseModel):
    message: str
    attention_score: int


class FocusMetrics(BaseModel):
    face_present: bool
    eyes_open_ratio: float
    eyes_closed_duration: float
    gaze_direction: str
    gaze_away_ratio: float
    head_pitch: float
    head_yaw: float


class AgentModeRequest(BaseModel):
    mode: str


class HealthBoostRequest(BaseModel):
    metrics: Optional[FocusMetrics] = None
    focus_score: Optional[float] = None


HEALTH_FOCUS_RESPONSES = {
    "face_absent": [
        "Looks like you stepped away — take a quick break, stretch, and come back refreshed.",
        "Camera can’t see you — if you’re here, adjust your position or lighting.",
        "You’ve been off-screen for a bit; re-center yourself before diving back in."
    ],
    "eyes_open_low": [
        "Your eyes look tired — close them for 10 seconds to rest them.",
        "Blink a few times or splash some water on your face; eye dryness kills focus fast.",
        "Try the 20-20-20 rule: every 20 minutes, look at something 20 ft away for 20 seconds."
    ],
    "eyes_closed_duration": [
        "You seem drowsy — take 3 deep breaths or stand up for a quick stretch.",
        "If you’re sleepy, a 5-minute walk or splash of cold water helps reset alertness.",
        "Try drinking a bit of water — dehydration often feels like fatigue."
    ],
    "gaze_direction": [
        "You’re looking away often — bring your eyes back to the screen and re-engage.",
        "Focus wandered off — what part of your notes needs your attention right now?",
        "If your mind drifted, try summarizing the last sentence you read out loud."
    ],
    "gaze_away_ratio": [
        "Your eyes have been off-screen for a while — take a 30-second reset, then refocus.",
        "Try minimizing distractions around you — your gaze keeps getting pulled away.",
        "Maybe it’s time to review goals for this study block — a quick refocus helps."
    ],
    "head_pitch": [
        "Looks like you’re looking down a lot — lift your head to ease neck strain.",
        "If you’re typing, great — but remember to look up occasionally to relax your neck.",
        "Head tilted down can reduce alertness; stretch your neck gently upwards."
    ],
    "head_yaw": [
        "Your head’s turning away — limit distractions in your peripheral view.",
        "Try facing the screen directly — this helps your mind align with your task.",
        "You’re glancing away — bring your attention back to the main window."
    ]
}

ALL_HEALTH_RESPONSES = [msg for responses in HEALTH_FOCUS_RESPONSES.values() for msg in responses]


def choose_health_intervention(metrics: Optional[FocusMetrics]):
    """Pick a context-aware micro-intervention based on focus metrics."""
    if metrics is None:
        return random.choice(ALL_HEALTH_RESPONSES), "general"

    if not metrics.face_present:
        return random.choice(HEALTH_FOCUS_RESPONSES["face_absent"]), "face_absent"

    if metrics.eyes_closed_duration >= 2.5:
        return random.choice(HEALTH_FOCUS_RESPONSES["eyes_closed_duration"]), "eyes_closed_duration"

    if metrics.eyes_open_ratio <= 0.3:
        return random.choice(HEALTH_FOCUS_RESPONSES["eyes_open_low"]), "eyes_open_low"

    gaze_direction = metrics.gaze_direction.lower()
    if gaze_direction not in {"center", "forward"}:
        return random.choice(HEALTH_FOCUS_RESPONSES["gaze_direction"]), "gaze_direction"

    if metrics.gaze_away_ratio >= 0.6:
        return random.choice(HEALTH_FOCUS_RESPONSES["gaze_away_ratio"]), "gaze_away_ratio"

    if metrics.head_pitch <= -25.0:
        return random.choice(HEALTH_FOCUS_RESPONSES["head_pitch"]), "head_pitch"

    if abs(metrics.head_yaw) >= 25.0:
        return random.choice(HEALTH_FOCUS_RESPONSES["head_yaw"]), "head_yaw"

    return random.choice(ALL_HEALTH_RESPONSES), "general"

@app.get("/")
async def root():
    return {"message": "FocusMind API is running"}


@app.get("/agent-mode")
async def get_agent_mode():
    """Return the currently active coaching agent."""
    return {"mode": agent_mode}


@app.post("/set-agent-mode")
async def set_agent_mode(request: AgentModeRequest):
    """Switch between motivational coach and health boost micro-interventions."""
    global agent_mode

    requested_mode = request.mode.lower()
    if requested_mode not in {"goggins", "health"}:
        raise HTTPException(status_code=400, detail="Invalid agent mode")

    agent_mode = requested_mode
    return {"success": True, "mode": agent_mode}


@app.get("/motivation", response_model=MotivationResponse)
async def get_motivation(reset: bool = False):
    """Get a motivational quote from David Goggins style coach"""
    global attention_score, focus_score_history
    
    # Reset attention score to 100 if requested (page refresh)
    if reset:
        attention_score = 100
        # Also reset focus history when starting a new session
        focus_score_history = []
    
    # Add initial score to history if it's the first entry
    if not focus_score_history:
        current_time = datetime.now().strftime("%H:%M:%S")
        focus_score_history.append({
            "timestamp": current_time,
            "focus_score": attention_score
        })
    
    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a study coach loosely inspired by David Goggins. Give intense, motivational study advice in a strictly PG version of his style. (No swearing). Keep it under 30 words."},
                {"role": "user", "content": "Give me motivation to study hard"}
            ],
            max_tokens=150
        )
        
        message = response.choices[0].message.content
        
        return MotivationResponse(message=message, attention_score=attention_score)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating motivation: {str(e)}")

@app.get("/attention-score")
async def get_attention_score():
    """Get current attention score"""
    global attention_score
    return {"attention_score": attention_score}

@app.post("/decrease-attention")
async def decrease_attention():
    """Decrease attention score by 15"""
    global attention_score, focus_score_history
    attention_score = max(0, attention_score - 15)  # Don't go below 0
    
    # Add to focus score history with timestamp
    current_time = datetime.now().strftime("%H:%M:%S")
    focus_score_history.append({
        "timestamp": current_time,
        "focus_score": attention_score
    })
    
    return {"attention_score": attention_score, "message": f"Attention score decreased to {attention_score}"}

@app.post("/get-focus-chart")
async def get_focus_chart():
    """Generate and return focus chart for the current session"""
    global focus_score_history
    
    try:
        if not focus_score_history:
            return {
                "success": False,
                "error": "No focus data available for chart generation"
            }
        
        # Generate chart
        png_path, chart_b64_bytes = generate_focus_chart_base64(focus_score_history)
        
        # Generate session stats
        session_stats = generate_session_stats(focus_score_history)
        
        return {
            "success": True,
            "chart_base64": chart_b64_bytes.decode("ascii"),
            "session_stats": session_stats,
            "png_filename": png_path,
            "data_points": len(focus_score_history)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating focus chart: {str(e)}")

@app.post("/reset-focus-session")
async def reset_focus_session():
    """Reset focus score history for a new session"""
    global focus_score_history
    focus_score_history = []
    return {"success": True, "message": "Focus session reset"}

@app.get("/focus-session-stats")
async def get_focus_session_stats():
    """Get current session statistics"""
    global focus_score_history
    
    if not focus_score_history:
        return {"data_points": 0, "session_active": False}
    
    stats = generate_session_stats(focus_score_history)
    return {
        "data_points": len(focus_score_history),
        "session_active": True,
        "stats": stats
    }

@app.post("/get-voice-nudge")
async def get_voice_nudge():
    """Get a motivational quote with voiceover by running nudge.py script with voice argument"""
    global attention_score
    try:
        # Run nudge.py script with 'voice' argument and current attention score
        result = subprocess.run(
            ["py", "nudge.py", "voice", str(attention_score)], 
            capture_output=True, 
            text=True, 
            cwd=os.path.dirname(os.path.abspath(__file__))
        )
        
        if result.returncode == 0:
            # Parse JSON output from nudge.py
            output_data = json.loads(result.stdout.strip())
            if output_data.get("success"):
                audio_filename = output_data.get("audio_file")
                audio_url = f"/audio/{audio_filename}" if audio_filename else None
                
                return {
                    "success": True,
                    "message": output_data["message"],
                    "audio_url": audio_url,
                    "audio_file": audio_filename,
                    "source": output_data.get("source", "David Goggins AI"),
                    "nudge_type": "voice",
                    "attention_score": attention_score  # Include current attention score
                }
            else:
                raise HTTPException(status_code=500, detail=f"Voice nudge script error: {output_data.get('error', 'Unknown error')}")
        else:
            raise HTTPException(status_code=500, detail=f"Script execution failed: {result.stderr}")
            
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse script output: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error running voice nudge script: {str(e)}")

class VoiceAudioRequest(BaseModel):
    message: str

@app.post("/generate-voice-audio")
async def generate_voice_audio(request: VoiceAudioRequest):
    """Generate voice audio for a specific message without getting a new quote"""
    try:
        # Use nudge.py to generate audio for the provided message
        result = subprocess.run(
            ["py", "nudge.py", "generate_audio", request.message], 
            capture_output=True, 
            text=True, 
            cwd=os.path.dirname(os.path.abspath(__file__))
        )
        
        if result.returncode == 0:
            # Parse JSON output from nudge.py
            output_data = json.loads(result.stdout.strip())
            if output_data.get("success"):
                audio_filename = output_data.get("audio_file")
                audio_url = f"/audio/{audio_filename}" if audio_filename else None
                
                return {
                    "success": True,
                    "message": request.message,
                    "audio_url": audio_url,
                    "audio_file": audio_filename,
                    "source": "David Goggins AI"
                }
            else:
                raise HTTPException(status_code=500, detail=f"Audio generation error: {output_data.get('error', 'Unknown error')}")
        else:
            raise HTTPException(status_code=500, detail=f"Script execution failed: {result.stderr}")
            
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse script output: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating voice audio: {str(e)}")


@app.post("/get-health-boost-nudge")
async def get_health_boost_nudge(request: Optional[HealthBoostRequest] = None):
    """Return a Health & Focus Boost micro-intervention based on the latest focus metrics."""
    global attention_score, last_focus_metrics

    if request is None:
        request = HealthBoostRequest()

    metrics = request.metrics or last_focus_metrics
    if request.metrics is not None:
        last_focus_metrics = request.metrics

    message, reason = choose_health_intervention(metrics)

    return {
        "success": True,
        "message": message,
        "source": "Health & Focus Boost",
        "nudge_type": "health_boost",
        "reason": reason,
        "focus_score": request.focus_score if request.focus_score is not None else attention_score,
        "attention_score": attention_score
    }

@app.post("/get-notification-nudge")
async def get_notification_nudge():
    """Send a system notification by running nudge.py script with notification argument"""
    global attention_score
    try:
        # Run nudge.py script with 'notification' argument and current attention score
        result = subprocess.run(
            ["py", "nudge.py", "notification", str(attention_score)], 
            capture_output=True, 
            text=True, 
            cwd=os.path.dirname(os.path.abspath(__file__))
        )

        if result.returncode == 0:
            # Parse JSON output from nudge.py
            output_data = json.loads(result.stdout.strip())
            if output_data.get("success"):
                return {
                    "success": True,
                    "message": output_data["message"],
                    "source": output_data.get("source", "AI study coach"),
                    "nudge_type": "notification",
                    "platform": output_data.get("platform", "unknown")
                }
            else:
                raise HTTPException(status_code=500, detail=f"Notification nudge script error: {output_data.get('error', 'Unknown error')}")
        else:
            raise HTTPException(status_code=500, detail=f"Script execution failed: {result.stderr}")
            
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse script output: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error running notification nudge script: {str(e)}")

@app.post("/get-break-nudge")
async def get_break_nudge():
    """Get a motivational break message for Pomodoro breaks"""
    try:
        # Run nudge.py script with 'break' argument (no attention score needed for breaks)
        result = subprocess.run(
            ["py", "nudge.py", "break"], 
            capture_output=True, 
            text=True, 
            cwd=os.path.dirname(os.path.abspath(__file__))
        )
        
        if result.returncode == 0:
            # Parse JSON output from nudge.py
            output_data = json.loads(result.stdout.strip())
            if output_data.get("success"):
                audio_filename = output_data.get("audio_file")
                audio_url = f"/audio/{audio_filename}" if audio_filename else None
                
                return {
                    "success": True,
                    "message": output_data["message"],
                    "audio_url": audio_url,
                    "audio_file": audio_filename,
                    "source": output_data.get("source", "David Goggins Break Coach"),
                    "nudge_type": "break"
                }
            else:
                raise HTTPException(status_code=500, detail=f"Break nudge script error: {output_data.get('error', 'Unknown error')}")
        else:
            raise HTTPException(status_code=500, detail=f"Script execution failed: {result.stderr}")
            
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse script output: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error running break nudge script: {str(e)}")

# Keep the old endpoint for backward compatibility
@app.post("/get-nudge-quote")
async def get_nudge_quote():
    """Get a motivational quote with voiceover (backward compatibility - calls voice nudge)"""
    return await get_voice_nudge()

# Face Tracking Integration Endpoints
class FocusScoreUpdate(BaseModel):
    focus_score: float
    metrics: Optional[FocusMetrics] = None


class AutoMotivationTrigger(BaseModel):
    threshold: int
    focus_score: float
    metrics: Optional[FocusMetrics] = None

@app.post("/update-focus-score")
async def update_focus_score(request: FocusScoreUpdate):
    """Update the attention score from face tracking system"""
    global attention_score, focus_score_history, last_focus_metrics

    # Update global attention score
    attention_score = max(0, min(100, request.focus_score))

    # Store latest focus metrics for health boost agent if provided
    if request.metrics is not None:
        last_focus_metrics = request.metrics

    # Add to focus score history for analytics
    focus_score_history.append({
        "timestamp": datetime.now(),
        "score": attention_score
    })
    
    # Keep only last 1000 entries to prevent memory issues
    if len(focus_score_history) > 1000:
        focus_score_history = focus_score_history[-1000:]
    
    return {
        "success": True,
        "updated_score": attention_score,
        "message": "Focus score updated successfully"
    }

@app.post("/trigger-auto-motivation")
async def trigger_auto_motivation(request: AutoMotivationTrigger):
    """Trigger automatic motivational quote when focus drops below thresholds"""
    global attention_score, agent_mode, last_focus_metrics

    try:
        print(f"🚨 Auto-motivation triggered! Focus dropped below {request.threshold}% (current: {request.focus_score:.1f}%)")

        if request.metrics is not None:
            last_focus_metrics = request.metrics

        metrics = request.metrics or last_focus_metrics

        if agent_mode.lower() == "health":
            message, reason = choose_health_intervention(metrics)

            response_data = {
                "success": True,
                "message": message,
                "source": "Health & Focus Boost",
                "nudge_type": "health_boost",
                "threshold": request.threshold,
                "focus_score": request.focus_score,
                "reason": reason
            }

            return response_data

        # Run nudge.py script with 'voice' argument and current attention score
        result = subprocess.run(
            ["py", "nudge.py", "voice", str(int(request.focus_score))],
            capture_output=True,
            text=True, 
            cwd=os.path.dirname(os.path.abspath(__file__))
        )
        
        if result.returncode == 0:
            # Parse JSON output from nudge.py
            output_data = json.loads(result.stdout.strip())
            if output_data.get("success"):
                audio_filename = output_data.get("audio_file")
                audio_url = f"/audio/{audio_filename}" if audio_filename else None
                
                return {
                    "success": True,
                    "message": output_data["message"],
                    "audio_url": audio_url,
                    "audio_file": audio_filename,
                    "source": output_data.get("source", "David Goggins AI"),
                    "nudge_type": "auto_voice",
                    "threshold": request.threshold,
                    "focus_score": request.focus_score
                }
            else:
                raise HTTPException(status_code=500, detail=f"Auto-motivation script error: {output_data.get('error', 'Unknown error')}")
        else:
            raise HTTPException(status_code=500, detail=f"Script execution failed: {result.stderr}")
            
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse script output: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error running auto-motivation script: {str(e)}")

@app.get("/face-tracking-status")
async def get_face_tracking_status():
    """Get the current status of face tracking."""
    global face_tracker, tracking_active, focus_score_history
    
    if face_tracker is None:
        return {
            "active": False,
            "score": None,
            "last_update": None,
            "message": "Face tracking not initialized"
        }
    
    return {
        "active": tracking_active,
        "score": focus_score_history[-1]["score"] if focus_score_history else None,
        "last_update": focus_score_history[-1]["timestamp"] if focus_score_history else None,
        "message": "Face tracking active" if tracking_active else "Face tracking paused"
    }

@app.post("/start-face-tracking")
async def start_face_tracking():
    """Start the face tracking system (placeholder for future implementation)"""
    # This could be enhanced to actually start the face tracking process
    # For now, it's a placeholder that the frontend can call
    return {
        "success": True,
        "message": "Face tracking start signal sent. Please run face_focus_tracker.py manually.",
        "command": "python3 face_focus_tracker.py --source 0"
    }

@app.post("/stop-face-tracking")
async def stop_face_tracking():
    """Stop the face tracking system (placeholder for future implementation)"""
    # This could be enhanced to actually stop the face tracking process
    return {
        "success": True,
        "message": "Face tracking stop signal sent."
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
