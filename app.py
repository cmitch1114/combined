from flask import Flask, render_template, request, jsonify, send_from_directory, redirect, session, url_for
import math
import os
import re
import sqlite3
import json
from dataclasses import asdict
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import hashlib
import secrets
from datetime import datetime, timedelta
import bcrypt

# Import blueprints
from blueprints.swimmers import swimmers_bp
from blueprints.coaches import coaches_bp
from blueprints.teams import teams_bp

# Import modules
from modules.database import (
    init_db, get_swimmer, get_all_swimmers, save_swimmer,
    create_team, get_team_by_code, verify_team_access, get_all_teams,
    create_training_group, get_team_training_groups, get_team_swimmers,
    get_swimmers_by_team_code, assign_swimmer_to_group
)
from modules.time_utils import (
    parse_time_input, format_time, format_time_precise, 
    adjust_time_for_practice, calculate_goal_times, round_interval_to_clock
)
from modules.swimmer_analysis import calculate_velocities, determine_swimmer_style, analyze_race_strategy
from modules.interval_calculator import (
    calculate_base_time, calculate_base_interval, 
    calculate_interval_fatigue, generate_intervals
)
from modules.colorsystem import UrbanchekColorSystem
from modules.swimming_program_builder import SwimmingProgramBuilder, TrainingPhase, TrainingGroup, Holiday, Macrocycle, Microcycle
from modules.workout_generator import WorkoutGenerator
from modules.workout_recommendation_engine import WorkoutRecommendationEngine
from modules.swimcloud_scraper import SwimCloudScraper
from modules.athlete_history import AthleteHistory
from modules.pulse_plot import PulsePlot
from modules.seasonal_workout_planner import SeasonalWorkoutPlanner

# Initialize Flask app
app = Flask(__name__, static_folder='static')
app.secret_key = 'your-secret-key-change-this'  # Change this to a secure secret key

# Initialize database and modules
init_db()
program_builder = SwimmingProgramBuilder()
workout_generator = WorkoutGenerator(program_builder)
recommendation_engine = WorkoutRecommendationEngine(program_builder)
seasonal_planner = SeasonalWorkoutPlanner()
swimcloud_scraper = SwimCloudScraper()
athlete_history = AthleteHistory(swimcloud_scraper)
pulse_plot = PulsePlot()

# Store scraper in app config for blueprint access
app.config['SWIMCLOUD_SCRAPER'] = swimcloud_scraper

@app.route('/search_swimmer', methods=['POST'])
def search_swimmer():
    """Search for swimmers on SwimCloud"""
    try:
        data = request.get_json()
        swimmer_name = data.get('swimmer_name', '').strip()

        if not swimmer_name:
            return jsonify({
                'success': False,
                'error': 'Swimmer name is required'
            })

        print(f"Searching SwimCloud for: {swimmer_name}")

        # Initialize scraper
        from modules.swimcloud_scraper import SwimCloudScraper
        scraper = SwimCloudScraper()

        # Search for swimmer
        search_results = scraper.search_swimmer(swimmer_name)

        if search_results and not any(result.get('error') for result in search_results):
            return jsonify({
                'success': True,
                'results': search_results,
                'message': f'Found {len(search_results)} swimmer(s)'
            })
        else:
            error_msg = 'No swimmers found'
            if search_results and search_results[0].get('error'):
                error_msg = search_results[0]['error']

            return jsonify({
                'success': False,
                'results': [],
                'error': error_msg
            })

    except Exception as e:
        print(f"Error searching swimmer: {str(e)}")
        return jsonify({
            'success': False,
            'results': [],
            'error': f'Search failed: {str(e)}'
        })

@app.route('/scrape_swimmer_times/<swimmer_id>', methods=['POST'])
def scrape_swimmer_times_by_id(swimmer_id):
    """Scrape swimmer times by SwimCloud ID"""
    try:
        data = request.get_json()
        profile_url = data.get('profile_url', f'https://www.swimcloud.com/swimmer/{swimmer_id}/')
        name = data.get('name', f'Swimmer {swimmer_id}')
        team = data.get('team', '')
        year = data.get('year', '')

        print(f"Scraping times for swimmer ID {swimmer_id}: {name}")

        # Initialize scraper
        from modules.swimcloud_scraper import SwimCloudScraper
        scraper = SwimCloudScraper()

        # Get times from SwimCloud
        times = scraper.get_swimmer_times(profile_url)

        if times:
            # Format times by event and course for best times lookup
            best_times = {}
            for time_entry in times:
                event_base = time_entry.get('event', '').replace(' Y ', ' ').replace(' L ', ' ').replace(' S ', ' ')
                course = time_entry.get('course', 'Y')

                if event_base:
                    # Create course-specific event keys like "50 Y Free", "100 L Free"
                    if course in ['Y', 'L', 'S']:
                        event_key = f"{event_base.replace(' Free', '').replace(' Back', '').replace(' Breast', '').replace(' Fly', '').replace(' IM', '').split()[0]} {course} {event_base.split()[-1]}"
                    else:
                        event_key = event_base

                    # Also create a standard format for comparison
                    standard_key = event_base

                    # Store both formats for flexibility
                    for key in [event_key, standard_key]:
                        if key not in best_times or time_entry.get('time_seconds', 999999) < best_times[key].get('time_seconds', 999999):
                            best_times[key] = {
                                'time': time_entry.get('time'),
                                'meet': time_entry.get('meet'),
                                'date': time_entry.get('date'),
                                'course': course,
                                'time_seconds': time_entry.get('time_seconds', 0),
                                'event': event_key
                            }

            # Save swimmer to database with enhanced info if available
            swimmer_data = {
                'id': int(swimmer_id),
                'name': name,
                'team': team,
                'year': year,
                'swimcloud_id': swimmer_id,
                'profile_url': profile_url
            }

            # Try to get enhanced swimmer info from the profile page
            try:
                enhanced_info = scraper._get_enhanced_swimmer_data({'swimcloud_id': swimmer_id, 'profile_url': profile_url})
                if enhanced_info:
                    if enhanced_info.get('team') and not team:
                        swimmer_data['team'] = enhanced_info['team']
                    if enhanced_info.get('location'):
                        swimmer_data['location'] = enhanced_info['location']
            except:
                pass

            # Save swimmer
            from modules.database import save_swimmer
            save_swimmer(swimmer_data)

            # Save times to database
            from modules.database import save_swimmer_times
            save_swimmer_times(int(swimmer_id), times)

            return jsonify({
                'success': True,
                'swimmer_info': {
                    'name': swimmer_data.get('name', name), 
                    'id': swimmer_id,
                    'team': swimmer_data.get('team', team),
                    'location': swimmer_data.get('location', '')
                },
                'best_times': best_times,
                'times_updated': len(times),
                'message': f'Successfully scraped {len(times)} times for {swimmer_data.get("name", name)}'
            })
        else:
            # Provide more specific error message based on what we tried
            error_message = 'No times found for this swimmer. This could be due to:'
            error_details = [
                '• SwimCloud may be temporarily blocking requests (HTTP 202 status)',
                '• The swimmer profile may be private or restricted',
                '• Network connectivity issues',
                '• SwimCloud server maintenance'
            ]

            suggestions = [
                '💡 **Try these solutions:**',
                '• Wait 5-10 minutes and try again',
                '• Verify the SwimCloud ID is correct',
                '• Check if the profile is publicly accessible on SwimCloud',
                '• Try during off-peak hours (early morning or late evening)'
            ]

            full_message = f"{error_message}\n\n" + '\n'.join(error_details) + '\n\n' + '\n'.join(suggestions)

            return jsonify({
                'success': False,
                'error': full_message,
                'retry_suggested': True,
                'swimmer_id': swimmer_id
            })

    except Exception as e:
        print(f"Error scraping swimmer times: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': f'Failed to scrape times: {str(e)}'
        })

# Register blueprints
app.register_blueprint(swimmers_bp, url_prefix='/api')
app.register_blueprint(coaches_bp, url_prefix='/api')
app.register_blueprint(teams_bp, url_prefix='/api')

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def check_team_access():
    """Check if user has valid team access"""
    return session.get('team_code') and session.get('team_id')

def get_current_team():
    """Get current team info from session"""
    if check_team_access():
        return {
            'team_code': session.get('team_code'),
            'team_id': session.get('team_id'),
            'team_name': session.get('team_name')
        }
    return None

def hash_password(password):
    """Hash a password using bcrypt"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password, hashed):
    """Verify a password against its hash"""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def generate_reset_token():
    """Generate a secure password reset token"""
    return secrets.token_urlsafe(32)

def is_logged_in():
    """Check if user is logged in"""
    return 'user_id' in session and session.get('user_id') is not None

def login_required(f):
    """Decorator to require login for routes"""
    def decorated_function(*args, **kwargs):
        if not is_logged_in():
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

# ============================================================================
# STATIC FILE SERVING
# ============================================================================

@app.route('/static/<path:path>')
def send_static(path):
    return send_from_directory('static', path)

# ============================================================================
# PAGE ROUTES
# ============================================================================

@app.route('/')
def index():
    """Landing page - redirect to login if not authenticated"""
    if is_logged_in():
        return redirect(url_for('home'))
    return redirect(url_for('login'))

@app.route('/home')
@login_required
def home():
    """Landing page with navigation to all features"""
    user_name = session.get('user_name', 'User')
    team_name = session.get('team_name', 'No Team')
    return render_template('home.html', user_name=user_name, team_name=team_name)

@app.route('/team_login')
def team_login():
    """Team login page"""
    return render_template('team_login.html')

@app.route('/login')
def login():
    """User login page"""
    if is_logged_in():
        return redirect(url_for('home'))
    return render_template('login.html')

@app.route('/register')
def register():
    """User registration page"""
    if is_logged_in():
        return redirect(url_for('home'))
    return render_template('register.html')

@app.route('/forgot_password')
def forgot_password():
    """Forgot password page"""
    if is_logged_in():
        return redirect(url_for('home'))
    return render_template('forgot_password.html')

@app.route('/forgot_username')
def forgot_username():
    """Forgot username page"""
    if is_logged_in():
        return redirect(url_for('home'))
    return render_template('forgot_username.html')

@app.route('/reset_password/<token>')
def reset_password(token):
    """Password reset page"""
    if is_logged_in():
        return redirect(url_for('home'))
    return render_template('reset_password.html', token=token)

@app.route('/team_setup')
def team_setup():
    """Team setup page for creating new teams"""
    return render_template('team_setup.html')

@app.route('/test_sets')
@app.route('/test_sets_index')
def test_sets():
    """Render the test sets page"""
    return render_template('test_sets.html')

@app.route('/urbanchek')
def urbanchek():
    """Render the urbanchek color system page"""
    return render_template('urbanchek.html')

@app.route('/debug-urbanchek')
def debug_urbanchek():
    """Debug version of Urbanchek color system page"""
    return render_template('debug-urbanchek.html')

@app.route('/database')
def database():
    """Render the database management page"""
    return render_template('database.html')

@app.route('/program_builder')
def program_builder_page():
    """Render the swimming program builder page"""
    return render_template('program_builder.html')

@app.route('/interval_calculator')
def interval_calculator():
    """Render the interval calculator page"""
    return render_template('interval_calculator.html')

@app.route('/pulse_plot')
def pulse_plot_page():
    """Render the pulse plot analysis page"""
    return render_template('pulse_plot.html')

@app.route('/athlete_profile')
def athlete_profile():
    """Render the athlete profile page"""
    return render_template('athlete_profile.html')

@app.route('/coaches')
def coaches():
    """Render the coaches page"""
    return render_template('coaches.html')

# ============================================================================
# AUTHENTICATION API
# ============================================================================

@app.route('/api/login', methods=['POST'])
def api_login():
    """Handle user login"""
    try:
        data = request.json
        username = data.get('username', '').strip()
        password = data.get('password', '')

        if not username or not password:
            return jsonify({"success": False, "error": "Username and password are required"}), 400

        from modules.database import get_user_by_username, update_user_login
        user = get_user_by_username(username)

        if not user or not verify_password(password, user['password_hash']):
            return jsonify({"success": False, "error": "Invalid username or password"}), 401

        # Update login timestamp
        update_user_login(user['id'])

        # Set session variables
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['user_name'] = user['full_name'] or user['username']
        session['user_email'] = user['email']

        if user['team_id']:
            session['team_id'] = user['team_id']
            session['team_name'] = user['team_name']
            session['team_code'] = user['team_code']

        return jsonify({
            "success": True,
            "message": f"Welcome back, {user['full_name'] or user['username']}!",
            "user": {
                "username": user['username'],
                "name": user['full_name'],
                "email": user['email'],
                "team_name": user.get('team_name')
            }
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/register', methods=['POST'])
def api_register():
    """Handle user registration"""
    try:
        data = request.json
        username = data.get('username', '').strip()
        email = data.get('email', '').strip()
        password = data.get('password', '')
        confirm_password = data.get('confirm_password', '')
        full_name = data.get('full_name', '').strip()
        team_name = data.get('team_name', '').strip()
        team_code = data.get('team_code', '').strip().upper()

        # Validation
        if not all([username, email, password, confirm_password, full_name]):
            return jsonify({"success": False, "error": "All fields are required"}), 400

        if password != confirm_password:
            return jsonify({"success": False, "error": "Passwords do not match"}), 400

        if len(password) < 6:
            return jsonify({"success": False, "error": "Password must be at least 6 characters"}), 400

        # Hash password
        password_hash = hash_password(password)

        # Handle team assignment - every user must have a team
        team_id = None
        existing_team_code = data.get('existing_team_code', '').strip().upper()

        if existing_team_code:
            # Join existing team
            from modules.database import get_team_by_code
            existing_team = get_team_by_code(existing_team_code)
            if not existing_team:
                return jsonify({"success": False, "error": f"Team with code '{existing_team_code}' not found"}), 400
            team_id = existing_team['id']
        elif team_name and team_code:
            # Create new team
            from modules.database import create_team, get_team_by_code
            try:
                existing_team = get_team_by_code(team_code)
                if existing_team:
                    return jsonify({"success": False, "error": "Team code already exists"}), 400
                team_id = create_team(team_name, team_code, None, full_name, email)
            except Exception as team_error:
                return jsonify({"success": False, "error": f"Team creation failed: {str(team_error)}"}), 400
        else:
            return jsonify({"success": False, "error": "You must either join an existing team or create a new one"}), 400

        # Create user
        from modules.database import create_user
        user_id = create_user(username, email, password_hash, full_name, team_id)

        return jsonify({
            "success": True,
            "message": "Registration successful! Please log in.",
            "user_id": user_id
        })

    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/logout', methods=['POST'])
def api_logout():
    """Handle user logout"""
    session.clear()
    return jsonify({"success": True, "message": "Logged out successfully"})

@app.route('/api/forgot_password', methods=['POST'])
def api_forgot_password():
    """Handle forgot password request"""
    try:
        data = request.json
        email = data.get('email', '').strip()

        if not email:
            return jsonify({"success": False, "error": "Email is required"}), 400

        from modules.database import get_user_by_email, set_password_reset_token
        user = get_user_by_email(email)

        if not user:
            # Don't reveal if email exists or not for security
            return jsonify({"success": True, "message": "If that email exists, a reset link has been sent."})

        # Generate reset token
        token = generate_reset_token()
        expires_at = datetime.now() + timedelta(hours=1)

        set_password_reset_token(email, token, expires_at)

        # Send reset email
        reset_url = f"{request.host_url}reset_password/{token}"
        subject = "Password Reset Request"
        content = f"""
Hello {user['full_name']},

You requested a password reset for your account. Click the link below to reset your password:

{reset_url}

This link will expire in 1 hour.

If you didn't request this reset, please ignore this email.

Best regards,
Swimming Training System
        """

        email_success, email_message = send_email_smtp(email, subject, content)

        if email_success:
            return jsonify({"success": True, "message": "Password reset link sent to your email."})
        else:
            return jsonify({"success": False, "error": "Failed to send reset email. Please try again later."}), 500

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/forgot_username', methods=['POST'])
def api_forgot_username():
    """Handle forgot username request"""
    try:
        data = request.json
        email = data.get('email', '').strip()

        if not email:
            return jsonify({"success": False, "error": "Email is required"}), 400

        from modules.database import get_user_by_email
        user = get_user_by_email(email)

        if not user:
            # Don't reveal if email exists or not for security
            return jsonify({"success": True, "message": "If that email exists, your username has been sent."})

        # Send username email
        subject = "Username Recovery"
        content = f"""
Hello {user['full_name']},

Your username is: {user['username']}

If you didn't request this information, please ignore this email.

Best regards,
Swimming Training System
        """

        email_success, email_message = send_email_smtp(email, subject, content)

        if email_success:
            return jsonify({"success": True, "message": "Username sent to your email."})
        else:
            return jsonify({"success": False, "error": "Failed to send username email. Please try again later."}), 500

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/reset_password', methods=['POST'])
def api_reset_password():
    """Handle password reset"""
    try:
        data = request.json
        token = data.get('token', '')
        password = data.get('password', '')
        confirm_password = data.get('confirm_password', '')

        if not all([token, password, confirm_password]):
            return jsonify({"success": False, "error": "All fields are required"}), 400

        if password != confirm_password:
            return jsonify({"success": False, "error": "Passwords do not match"}), 400

        if len(password) < 6:
            return jsonify({"success": False, "error": "Password must be at least 6 characters"}), 400

        from modules.database import get_user_by_reset_token, update_user_password
        user = get_user_by_reset_token(token)

        if not user:
            return jsonify({"success": False, "error": "Invalid or expired reset token"}), 400

        # Update password
        password_hash = hash_password(password)
        update_user_password(user['id'], password_hash)

        return jsonify({"success": True, "message": "Password reset successful! Please log in with your new password."})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ============================================================================
# TEAM MANAGEMENT API
# ============================================================================

@app.route('/api/team_login', methods=['POST'])
def api_team_login():
    """Handle team login"""
    try:
        data = request.json
        team_code = data.get('team_code', '').strip()
        password = data.get('password', '')

        if not team_code:
            return jsonify({"success": False, "error": "Team code is required"}), 400

        if not verify_team_access(team_code, password):
            return jsonify({"success": False, "error": "Invalid team code or password"}), 401

        team = get_team_by_code(team_code)
        if not team:
            return jsonify({"success": False, "error": "Team not found"}), 404

        session['team_code'] = team_code
        session['team_id'] = team['id']
        session['team_name'] = team['team_name']

        return jsonify({
            "success": True,
            "team_name": team['team_name'],
            "team_code": team_code
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/team_logout', methods=['POST'])
def api_team_logout():
    """Handle team logout"""
    session.clear()
    return jsonify({"success": True})

@app.route('/api/create_team', methods=['POST'])
def api_create_team():
    """Create a new team"""
    try:
        data = request.json
        team_name = data.get('team_name', '').strip()
        team_code = data.get('team_code', '').strip().upper()
        access_password = data.get('access_password', '').strip()
        coach_name = data.get('coach_name', '').strip()
        contact_email = data.get('contact_email', '').strip()

        if not team_name or not team_code:
            return jsonify({"success": False, "error": "Team name and team code are required"}), 400

        team_id = create_team(team_name, team_code, access_password or None, coach_name or None, contact_email or None)

        return jsonify({
            "success": True,
            "team_id": team_id,
            "message": f"Team '{team_name}' created successfully with code '{team_code}'"
        })

    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/team_training_groups')
def get_team_training_groups_api():
    """Get training groups for current team"""
    try:
        if not check_team_access():
            return jsonify({"error": "Team access required"}), 401

        team_id = session.get('team_id')
        groups = get_team_training_groups(team_id)
        return jsonify({"success": True, "groups": groups})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================================================
# COACHES API
# ============================================================================

@app.route('/api/coaches')
def get_coaches():
    """Get all coaches"""
    try:
        from modules.database import get_all_coaches
        coaches = get_all_coaches()
        return jsonify(coaches)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/team_coaches')
def get_team_coaches():
    """Get coaches for current team"""
    try:
        if not check_team_access():
            return jsonify({"error": "Team access required"}), 401

        team_id = session.get('team_id')
        from modules.database import get_team_coaches
        coaches = get_team_coaches(team_id)
        return jsonify(coaches)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/coach/<int:coach_id>')
def get_coach_by_id(coach_id):
    """Get a specific coach by ID"""
    try:
        from modules.database import get_coach
        coach = get_coach(coach_id)
        if coach:
            return jsonify(coach)
        else:
            return jsonify({"error": f"No coach found with ID {coach_id}"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/save_coach', methods=['POST'])
def save_coach_endpoint():
    """Save coach data to database"""
    try:
        data = request.json
        coach_id = data.get('id')
        name = data.get('name', '').strip()

        if not name:
            return jsonify({"success": False, "error": "Coach name is required"}), 400

        # Add team_id if user has team access
        if check_team_access():
            team_id = session.get('team_id')
            data['team_id'] = team_id

        from modules.database import save_coach
        coach_id = save_coach(data)

        return jsonify({
            "success": True,
            "id": coach_id,
            "message": "Coach saved successfully"
        })

    except Exception as e:
        print(f"Error saving coach: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/coach/<int:coach_id>', methods=['DELETE'])
def delete_coach_endpoint(coach_id):
    """Delete a coach from the database"""
    try:
        from modules.database import delete_coach
        delete_coach(coach_id)
        return jsonify({"success": True, "message": "Coach deleted successfully"})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 404
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/coach_groups/<int:coach_id>')
def get_coach_groups(coach_id):
    """Get training groups for a specific coach"""
    try:
        from modules.database import get_coach_training_groups
        groups = get_coach_training_groups(coach_id)
        return jsonify(groups)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/create_training_group', methods=['POST'])
def create_training_group_api():
    """Create a new training group"""
    try:
        if not check_team_access():
            return jsonify({"success": False, "error": "Team access required"}), 401

        data = request.json
        group_name = data.get('group_name', '').strip()
        group_description = data.get('group_description', '').strip()
        coach_name = data.get('coach_name', '').strip()
        age_range = data.get('age_range', '').strip()
        skill_level = data.get('skill_level', '').strip()
        coach_id = data.get('coach_id')  # Optional coach ID

        if not group_name:
            return jsonify({"success": False, "error": "Group name is required"}), 400

        team_id = session.get('team_id')

        # Create the training group
        group_id = create_training_group(
            team_id=team_id,
            group_name=group_name,
            group_description=group_description,
            coach_name=coach_name,
            age_range=age_range,
            skill_level=skill_level
        )

        return jsonify({
            "success": True,
            "group_id": group_id,
            "message": f"Training group '{group_name}' created successfully"
        })

    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/assign_coach_to_group', methods=['POST'])
def assign_coach_to_group():
    """Assign a coach to a training group"""
    try:
        data = request.json
        coach_id = data.get('coach_id')
        group_id = data.get('group_id')
        if not coach_id or not group_id:
            return jsonify({"success": False, "error": "Coach ID and Group ID are required"}), 400

        # Get coach name
        from modules.database import get_coach, get_connection
        coach = get_coach(coach_id)
        if not coach:
            return jsonify({"success": False, "error": "Coach not found"}), 404

        # Update the training group with coach name
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE training_groups SET coach_name = ? WHERE id = ?', (coach['name'], group_id))
        conn.commit()
        conn.close()

        return jsonify({"success": True, "message": "Coach assigned to group successfully"})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/remove_coach_from_group', methods=['POST'])
def remove_coach_from_group():
    """Remove a coach from a training group"""
    print(f"remove_coach_from_group endpoint called")

    conn = None
    try:
        data = request.json
        if not data:
            return jsonify({"success": False, "error": "No data provided"}), 400

        coach_id = data.get('coach_id')
        group_name = data.get('group_name')

        print(f"Received data: coach_id={coach_id}, group_name={group_name}")

        if not coach_id or not group_name:
            return jsonify({"success": False, "error": "Coach ID and Group Name are required"}), 400

        # Get coach details first
        from modules.database import get_coach, get_connection
        coach = get_coach(coach_id)
        if not coach:
            return jsonify({"success": False, "error": "Coach not found"}), 404

        print(f"Found coach: {coach['name']}")

        # Remove coach from the training group by setting coach_name to NULL
        conn = get_connection()
        cursor = conn.cursor()

        # First, let's see what's actually in the database
        cursor.execute('''
            SELECT id, group_name, coach_name FROM training_groups 
            WHERE group_name = ?
        ''', (group_name,))

        existing_groups = cursor.fetchall()
        print(f"Groups with name '{group_name}':")
        for group in existing_groups:
            print(f"  ID: {group[0]}, Name: '{group[1]}', Coach: '{group[2]}'")

        # Also check all groups for this coach
        cursor.execute('''
            SELECT id, group_name, coach_name FROM training_groups 
            WHERE coach_name = ?
        ''', (coach['name'],))

        coach_groups = cursor.fetchall()
        print(f"Groups assigned to coach '{coach['name']}':")
        for group in coach_groups:
            print(f"  ID: {group[0]}, Name: '{group[1]}', Coach: '{group[2]}'")

        # Update the training group to remove coach assignment
        cursor.execute('''
            UPDATE training_groups 
            SET coach_name = NULL 
            WHERE coach_name = ? AND group_name = ?
        ''', (coach['name'], group_name))

        rows_affected = cursor.rowcount
        print(f"Rows affected: {rows_affected}")

        if rows_affected > 0:
            conn.commit()
            print("Successfully removed coach from group")
            return jsonify({"success": True, "message": "Coach removed from group successfully"})
        else:
            # Check if the group exists
            cursor.execute('''
                SELECT coach_name FROM training_groups 
                WHERE group_name = ?
            ''', (group_name,))

            group_result = cursor.fetchone()

            if not group_result:
                return jsonify({"success": False, "error": f"Training group '{group_name}' not found"}), 404
            else:
                current_coach = group_result[0]
                if not current_coach or current_coach.strip() == '':
                    # Group exists but has no coach assigned - treat as success since goal is achieved
                    conn.commit()
                    return jsonify({"success": True, "message": "Group already has no coach assigned"})
                else:
                    return jsonify({"success": False, "error": f"Coach '{coach['name']}' is not assigned to group '{group_name}' (currently assigned to '{current_coach}')"})

    except Exception as e:
        print(f"Error in remove_coach_from_group: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

    finally:
        if conn:
            conn.close()

@app.route('/api/delete_training_group/<int:group_id>', methods=['DELETE'])
def delete_training_group_endpoint(group_id):
    """Delete a training group"""
    try:
        from modules.database import delete_training_group
        delete_training_group(group_id)
        return jsonify({"success": True, "message": "Training group deleted successfully"})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 404
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/training_group/<int:group_id>')
def get_training_group_by_id_endpoint(group_id):
    """Get a specific training group by ID"""
    try:
        from modules.database import get_training_group_by_id
        group = get_training_group_by_id(group_id)
        if group:
            return jsonify(group)
        else:
            return jsonify({"error": f"No training group found with ID {group_id}"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/athlete_coaches/<int:swimmer_id>', methods=['GET'])
def get_athlete_coaches_api(swimmer_id):
    """Get all coaches for an athlete"""
    try:
        from modules.database import get_athlete_coaches
        coaches = get_athlete_coaches(swimmer_id)
        return jsonify({"success": True, "coaches": coaches})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/swimmer/<int:swimmer_id>')
def get_swimmer_api(swimmer_id):
    """API endpoint to get swimmer data - used by athlete profile"""
    try:
        from modules.database import get_swimmer
        swimmer = get_swimmer(swimmer_id)
        if swimmer:
            return jsonify(swimmer)
        else:
            return jsonify({"error": f"No swimmer found with ID {swimmer_id}"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/athlete_coaches/<int:swimmer_id>', methods=['POST'])
def save_athlete_coaches_api(swimmer_id):
    """Save multiple coaches for an athlete"""
    try:
        data = request.json
        coach_ids = data.get('coach_ids', [])
        primary_coach_id = data.get('primary_coach_id')

        from modules.database import save_athlete_coaches
        success = save_athlete_coaches(swimmer_id, coach_ids, primary_coach_id)

        if success:
            return jsonify({"success": True, "message": "Coaches saved successfully"})
        else:
            return jsonify({"success": False, "error": "Failed to save coaches"}), 500

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500



# ============================================================================
# INTERVAL CALCULATION API
# ============================================================================

@app.route('/generate', methods=['POST'])
def generate():
    """Generate intervals based on swimmer times"""
    try:
        data = request.json

        times = {
            't50': parse_time_input(data.get('t50', '')),
            't100': parse_time_input(data.get('t100', '')),
            't200': parse_time_input(data.get('t200', '')),
            't500': parse_time_input(data.get('t500', '')),
        }

        goal_times = {
            'g50': parse_time_input(data.get('g50', '')),
            'g100': parse_time_input(data.get('g100', '')),
            'g200': parse_time_input(data.get('g200', '')),
            'g500': parse_time_input(data.get('g500', '')),
        }

        goal_percentage = float(data.get('goal_percentage', 2.0))
        num_reps = int(data.get('num_reps', 3))
        base_interval_adjustment = data.get('base_interval_adjustment', 10)
        default_effort = data.get('default_effort', '90% Effort')

        calculated_goal_times = calculate_goal_times(times, goal_percentage)

        if goal_times['g50'] <= 0 and calculated_goal_times.get('g50', 0) > 0:
            goal_times['g50'] = calculated_goal_times['g50']
        if goal_times['g100'] <= 0 and calculated_goal_times.get('g100', 0) > 0:
            goal_times['g100'] = calculated_goal_times['g100']
        if goal_times['g200'] <= 0 and calculated_goal_times.get('g200', 0) > 0:
            goal_times['g200'] = calculated_goal_times['g200']
        if goal_times['g500'] <= 0 and calculated_goal_times.get('g500', 0) > 0:
            goal_times['g500'] = calculated_goal_times['g500']

        velocities = calculate_velocities(times)
        goal_velocities = {}

        if goal_times['g50'] > 0:
            goal_velocities['50'] = 50 / goal_times['g50']
        if goal_times['g100'] > 0:
            goal_velocities['100'] = 100 / goal_times['g100']
        if goal_times['g200'] > 0:
            goal_velocities['200'] = 200 / goal_times['g200']
        if goal_times['g500'] > 0:
            goal_velocities['500'] = 500 / goal_times['g500']

        swimmer_style, dropoff = determine_swimmer_style(velocities)

        base_interval_100 = calculate_base_interval(times['t100'], swimmer_style)
        distances = [25, 50, 75, 100, 125, 150, 175, 200, 225, 250, 275, 300, 325, 350, 375, 400, 425, 450, 475, 500]

        intervals, fatigue_progressions = generate_intervals(times, distances, swimmer_style, num_reps)

        actual_times = {
            "50 yards": format_time(times['t50']) if times['t50'] > 0 else None,
            "100 yards": format_time(times['t100']) if times['t100'] > 0 else None,
            "200 yards": format_time(times['t200']) if times['t200'] > 0 else None,
            "500 yards": format_time(times['t500']) if times['t500'] > 0 else None
        }

        model_predictions = {}
        practice_predictions = {}

        for distance in distances:
            base_time = calculate_base_time(distance, times, velocities, swimmer_style)

            if base_time > 0:
                distance_key = f"{distance} yards"
                model_predictions[distance_key] = format_time(base_time)
                practice_time = adjust_time_for_practice(base_time, distance)
                practice_predictions[distance_key] = format_time(practice_time)

        goal_predictions = {}

        for distance in distances:
            base_time = calculate_base_time(distance, times, velocities, swimmer_style)

            if base_time > 0:
                goal_time = base_time * (1 - goal_percentage/100)
                distance_key = f"{distance} yards"
                goal_predictions[distance_key] = format_time(goal_time)

        response = {
            "intervals": intervals,
            "fatigue_progressions": fatigue_progressions,
            "actual_times": actual_times,
            "model_predictions": model_predictions,
            "practice_predictions": practice_predictions,
            "goal_model": {
                "formula": f"Goal times based on {goal_percentage}% improvement",
                "percentage": goal_percentage
            },
            "goal_predictions": goal_predictions,
            "velocity_model": {
                "formula": f"Cubic model based on {swimmer_style} profile"
            },
            "swimmer_profile": {
                "style": swimmer_style,
                "base_interval_100": format_time(base_interval_100)
            }
        }

        return jsonify(response)

    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Error in generate: {str(e)}\n{error_trace}")
        return jsonify({"error": str(e), "trace": error_trace}), 400

# ============================================================================
# COLOR SYSTEM API
# ============================================================================

@app.route('/calculate_color_system', methods=['POST'])
def calculate_color_system():
    """Calculates and returns the Urbanchek color system results"""
    try:
        test_type = request.json.get('test_type', '200_test')
        minutes = int(request.json.get('minutes', 0))
        seconds = float(request.json.get('seconds', 0))
        drag_suit = request.json.get('drag_suit', False)
        course = request.json.get('course', 'SCY')
        stroke = request.json.get('stroke', 'freestyle')

        total_seconds = minutes * 60 + seconds

        color_system = UrbanchekColorSystem()
        results = color_system.calculate_full_system(test_type, total_seconds, drag_suit)

        return jsonify(results)

    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Error in calculate_color_system: {str(e)}\n{error_trace}")
        return jsonify({'error': str(e)}), 400

# ============================================================================
# PULSE PLOT API
# ============================================================================

@app.route('/api/generate_pulse_plot', methods=['POST'])
def generate_pulse_plot():
    """Process pulse data and generate analysis for Salo Pulse Plot Test"""
    try:
        data = request.json
        swimmer_name = data.get('swimmer_name')
        swimmer_id = data.get('swimmer_id')
        test_date = data.get('test_date')
        stroke = data.get('stroke', 'freestyle')
        interval_distance = int(data.get('interval_distance', 100))

        hr_10s = data.get('hr_10s', [])
        hr_30s = data.get('hr_30s', [])
        hr_60s = data.get('hr_60s', [])
        swim_times = data.get('swim_times', [])

        if not swimmer_name or not test_date:
            return jsonify({'error': 'Missing swimmer name or test date'}), 400

        if len(hr_10s) != 8 or len(hr_30s) != 8 or len(hr_60s) != 8 or len(swim_times) != 8:
            return jsonify({'error': 'Salo Pulse Plot requires 8 sets of measurements'}), 400

        swim_speeds = [interval_distance / time if time > 0 else 0 for time in swim_times]

        # Convert heart rate counts to actual heart rates and sum them
        sum_heart_rates = []
        for i in range(8):
            try:
                # Convert 10-second counts to heart rates (multiply by 6) then sum
                hr_10_bpm = int(hr_10s[i]) * 6
                hr_30_bpm = int(hr_30s[i]) * 6
                hr_60_bpm = int(hr_60s[i]) * 6
                hr_sum = hr_10_bpm + hr_30_bpm + hr_60_bpm
                sum_heart_rates.append(hr_sum)
            except (ValueError, IndexError, TypeError):
                sum_heart_rates.append(0)

        import base64
        from io import BytesIO
        import matplotlib.pyplot as plt
        import numpy as np

        plt.figure(figsize=(10, 6))
        plt.scatter(swim_speeds, sum_heart_rates)

        if all(speed > 0 for speed in swim_speeds) and all(hr > 0 for hr in sum_heart_rates):
            slope, intercept = np.polyfit(swim_speeds, sum_heart_rates, 1)
            fit_line = np.poly1d((slope, intercept))
            fit_speeds = np.linspace(min(swim_speeds), max(swim_speeds), 100)
            plt.plot(fit_speeds, fit_line(fit_speeds), 'r--')
            equation = f"HR Sum = {slope:.2f} × Speed + {intercept:.2f}"
            plt.text(min(swim_speeds), max(sum_heart_rates), fontsize=10)

        plt.title(f"Pulse Plot - {swimmer_name} - {test_date}")
        plt.xlabel("Swim Speed (yards/second)")
        plt.ylabel("Heart Rate Sum (10s + 30s + 60s)")
        plt.grid(True)

        buf = BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        plot_image = base64.b64encode(buf.read()).decode('utf-8')
        plt.close()

        # Load historical data for comparison
        history = []
        if swimmer_id:
            try:
                history = pulse_plot.load_history_from_db(swimmer_id)
            except Exception as e:
                print(f"Warning: Could not load historical data: {e}")
                # Try loading from file as backup
                try:
                    history = pulse_plot.load_history(swimmer_name)
                except Exception as e2:
                    print(f"Warning: Could not load file history either: {e2}")

        # Save the test results to database and file
        save_result = pulse_plot.save_test(
            swimmer_id=swimmer_id,
            swimmer_name=swimmer_name,
            test_date=test_date,
            swim_times=swim_times,
            hr_10s=hr_10s,
            hr_30s=hr_30s,
            hr_60s=hr_60s,
            stroke=stroke
        )

        if save_result.get('success'):
            print(f"Successfully saved pulse plot test for {swimmer_name} on {test_date}")
        else:
            print(f"Warning: Failed to save test data: {save_result.get('error')}")

        # Enhanced Dave Salo analysis
        analysis_parts = []
        training_recommendations = []

        if 'slope' in locals() and 'intercept' in locals():
            # Heart Rate Response Analysis
            if slope > 60:
                analysis_parts.append("🔴 **STEEP HEART RATE RESPONSE**: Your heart rate increases dramatically with speed changes. This indicates limited aerobic conditioning and suggests your anaerobic threshold is being reached quickly.")
                training_recommendations.extend([
                    "Focus on aerobic base building with longer, easier sets",
                    "Incorporate more threshold training at moderate intensities",
                    "Reduce high-intensity work until aerobic base improves"
                ])
            elif slope > 40:
                analysis_parts.append("🟡 **MODERATE HEART RATE RESPONSE**: Your cardiovascular system shows moderate efficiency. There's room for improvement in aerobic conditioning.")
                training_recommendations.extend([
                    "Balance aerobic base work with threshold training",
                    "Include progressive speed work with adequate recovery",
                    "Monitor heart rate during training to stay in appropriate zones"
                ])
            elif slope > 20:
                analysis_parts.append("🟢 **GOOD HEART RATE CONTROL**: Your heart rate response shows good aerobic conditioning. You're efficiently managing cardiovascular stress across speed changes.")
                training_recommendations.extend([
                    "Maintain current aerobic base with continued volume",
                    "Can handle more high-intensity training",
                    "Focus on race-pace and lactate tolerance work"
                ])
            else:
                analysis_parts.append("🔵 **EXCELLENT CARDIOVASCULAR EFFICIENCY**: Your heart rate remains remarkably stable across speed changes. This indicates superior aerobic conditioning and cardiovascular efficiency.")
                training_recommendations.extend([
                    "Excellent aerobic base - can handle high training loads",
                    "Focus on speed and power development",
                    "Incorporate race-specific training at higher intensities"
                ])

            # Intercept Analysis (Resting/Base Heart Rate Response)
            avg_hr_sum = sum(sum_heart_rates) / len(sum_heart_rates)
            if avg_hr_sum > 450:
                analysis_parts.append("📈 **HIGH BASELINE RESPONSE**: Your overall heart rate levels are elevated, suggesting either high training stress, incomplete recovery, or lower cardiovascular fitness.")
                training_recommendations.append("Consider increasing recovery time between intense sessions")
            elif avg_hr_sum < 300:
                analysis_parts.append("📉 **LOW BASELINE RESPONSE**: Your heart rate levels are quite low, indicating either excellent cardiovascular fitness or potentially undertrained state.")
                training_recommendations.append("Monitor for signs of overtraining or undertraining")

            # Speed Range Analysis
            speed_range = max(swim_speeds) - min(swim_speeds)
            if speed_range < 0.1:
                analysis_parts.append("⚠️ **LIMITED SPEED RANGE**: The test shows minimal speed variation. Ensure you're following the protocol correctly with varying intensities from easy to maximum effort.")

            # Recovery Analysis (comparing heart rates at different time points)
            hr_recovery_pattern = []
            for i in range(8):
                if hr_10s[i] > 0 and hr_60s[i] > 0:
                    recovery_ratio = hr_60s[i] / hr_10s[i] if hr_10s[i] > 0 else 1
                    hr_recovery_pattern.append(recovery_ratio)

            if hr_recovery_pattern:
                avg_recovery = sum(hr_recovery_pattern) / len(hr_recovery_pattern)
                if avg_recovery > 0.8:
                    analysis_parts.append("🔄 **SLOW HEART RATE RECOVERY**: Your heart rate doesn't drop significantly during the 60-second recovery periods. This suggests limited cardiovascular recovery capacity.")
                    training_recommendations.append("Include more recovery-focused training and active rest periods")
                elif avg_recovery < 0.6:
                    analysis_parts.append("⚡ **EXCELLENT RECOVERY**: Your heart rate drops well during recovery periods, indicating good cardiovascular recovery capacity.")

        else:
            analysis_parts.append("Unable to calculate detailed trend analysis. Ensure all data points are valid.")

        # Training Phase Recommendations
        analysis_parts.append("\n**TRAINING PHASE RECOMMENDATIONS:**")
        if slope > 50:
            analysis_parts.append("• **Base Phase**: Focus on aerobic development (70-80% of training)")
            analysis_parts.append("• **Volume**: Increase weekly training distance gradually")
            analysis_parts.append("• **Intensity**: Keep 80% of training at aerobic intensities")
        elif slope > 30:
            analysis_parts.append("• **Build Phase**: Balance base and threshold work (60% aerobic, 30% threshold, 10% speed)")
            analysis_parts.append("• **Lactate Threshold**: Include regular threshold sets 2-3x per week")
        else:
            analysis_parts.append("• **Competition Phase**: Focus on race-pace and speed work")
            analysis_parts.append("• **Race Preparation**: Include regular race-pace training")
            analysis_parts.append("• **Taper**: Consider reducing volume while maintaining intensity")

        # Retesting Recommendations
        analysis_parts.append("\n**RETESTING PROTOCOL:**")
        analysis_parts.append("• Retest every 4-6 weeks to track cardiovascular adaptations")
        analysis_parts.append("• Perform test in similar conditions (time of day, rest level)")
        analysis_parts.append("• Look for downward trend in heart rate at same speeds (improved fitness)")
        analysis_parts.append("• Monitor for flattening of the slope (better aerobic conditioning)")

        analysis = "\n".join(analysis_parts)
        if training_recommendations:
            analysis += "\n\n**SPECIFIC TRAINING RECOMMENDATIONS:**\n• " + "\n• ".join(training_recommendations)

        return jsonify({
            'success': True,
            'swimmer_name': swimmer_name,
            'test_date': test_date,
            'stroke': stroke,
            'interval_distance': interval_distance,
            'swim_times': swim_times,
            'swim_speeds': swim_speeds,
            'sum_heart_rates': sum_heart_rates,
            'plot_image': plot_image,
            'analysis': analysis,
            'save_status': save_result,
            'historical_tests_count': len(history) if history else 0,
            'message': f"Test saved successfully for {swimmer_name} on {test_date}" if save_result.get('success') else "Test completed but save failed"
        })

    except Exception as e:
        import traceback
        error_msg = str(e)
        print(f"Error generating pulse plot: {error_msg}")
        print(f"Data received: {data}")
        print(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': error_msg,
            'debug_data': {
                'swimmer_name': data.get('swimmer_name'),
                'test_date': data.get('test_date'),
                'hr_10s_length': len(data.get('hr_10s', [])),
                'hr_30s_length': len(data.get('hr_30s', [])),
                'hr_60s_length': len(data.get('hr_60s', [])),
                'swim_times_length': len(data.get('swim_times', [])),
            }
        }), 500

@app.route('/api/pulse_plot_history/<int:swimmer_id>')
def get_pulse_plot_history(swimmer_id):
    """Get pulse plot test history for a swimmer"""
    try:
        history = pulse_plot.load_history_from_db(swimmer_id)

        return jsonify({
            'success': True,
            'swimmer_id': swimmer_id,
            'history': history,
            'test_count': len(history)
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/swimmer/<int:swimmer_id>')
def get_swimmer_data(swimmer_id):
    """Get swimmer data for interval calculator and other pages"""
    try:
        from modules.database import get_swimmer
        swimmer = get_swimmer(swimmer_id)
        if swimmer:
            return jsonify(swimmer)
        else:
            return jsonify({"error": f"No swimmer found with ID {swimmer_id}"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/swimmer/<int:swimmer_id>/best_times')
def get_swimmer_best_times_route(swimmer_id):
    """Get best times for a swimmer - used by athlete profile"""
    try:
        from modules.database import get_swimmer_best_times, get_swimmer_time_history

        # Get both best times and all times history
        best_times = get_swimmer_best_times(swimmer_id)
        all_times = get_swimmer_time_history(swimmer_id)

        print(f"📊 Loading times for swimmer {swimmer_id}")
        print(f"📋 Found {len(best_times) if best_times else 0} best times")
        print(f"📋 Found {len(all_times) if all_times else 0} total times")

        if best_times:
            # Log first few times for debugging
            for i, time_entry in enumerate(best_times[:3]):
                print(f"  Best time {i+1}: {time_entry.get('event')} - {time_entry.get('time_string')} ({time_entry.get('course')})")

        # Ensure we return an empty list instead of None
        if not best_times:
            best_times = []
        if not all_times:
            all_times = []

        return jsonify({
            "success": True, 
            "times": best_times,  # For athlete profile compatibility
            "best_times": best_times, 
            "all_times": all_times,  # All times for history display
            "count": len(best_times),
            "total_times": len(all_times),
            "swimmer_id": swimmer_id
        })
    except Exception as e:
        print(f"❌ Error getting swimmer times for {swimmer_id}: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False, 
            "error": str(e),
            "times": [],
            "best_times": [],
            "all_times": [],
            "count": 0
        }), 500

@app.route('/api/athlete_pulse_history/<int:swimmer_id>')
def get_athlete_pulse_history(swimmer_id):
    """Get formatted pulse plot history for athlete profile display"""
    try:
        from modules.database import get_connection
        conn = get_connection()
        cursor = conn.cursor()

        # First check if the table exists
        cursor.execute('''
            SELECT name FROM sqlite_master WHERE type='table' AND name='pulse_plot_tests'
        ''')

        if not cursor.fetchone():
            # Table doesn't exist, return empty results
            conn.close()
            return jsonify({
                'success': True,
                'swimmer_id': swimmer_id,
                'pulse_tests': [],
                'test_count': 0
            })

        cursor.execute('''
            SELECT test_date, stroke, swim_times, hr_10s, hr_30s, hr_60s, swim_speeds, sum_heart_rates, created_at
            FROM pulse_plot_tests 
            WHERE swimmer_id = ? 
            ORDER BY test_date DESC, created_at DESC
        ''', (swimmer_id,))

        rows = cursor.fetchall()
        conn.close()

        formatted_history = []
        for row in rows:
            try:
                test_data = {
                    'test_date': row[0],
                    'stroke': row[1] if row[1] else 'freestyle',
                    'swim_times': json.loads(row[2]) if row[2] else [],
                    'hr_10s': json.loads(row[3]) if row[3] else [],
                    'hr_30s': json.loads(row[4]) if row[4] else [],
                    'hr_60s': json.loads(row[5]) if row[5] else [],
                    'swim_speeds': json.loads(row[6]) if row[6] else [],
                    'sum_heart_rates': json.loads(row[7]) if row[7] else [],
                    'created_at': row[8]
                }

                # Calculate summary statistics
                if test_data['swim_speeds'] and test_data['sum_heart_rates']:
                    test_data['avg_speed'] = sum(test_data['swim_speeds']) / len(test_data['swim_speeds'])
                    test_data['avg_hr_sum'] = sum(test_data['sum_heart_rates'])/ len(test_data['sum_heart_rates'])
                    test_data['speed_range'] = max(test_data['swim_speeds']) - min(test_data['swim_speeds'])
                    test_data['hr_range'] = max(test_data['sum_heart_rates']) - min(test_data['sum_heart_rates'])

                formatted_history.append(test_data)
            except (json.JSONDecodeError, ValueError) as e:
                print(f"Error parsing pulse plot data for row: {e}")
                continue

        return jsonify({
            'success': True,
            'swimmer_id': swimmer_id,
            'pulse_tests': formatted_history,
            'test_count': len(formatted_history)
        })

    except Exception as e:
        print(f"Error in get_athlete_pulse_history: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'swimmer_id': swimmer_id,
            'pulse_tests': [],
            'test_count': 0
        }), 200  # Return 200 instead of 500 to prevent frontend errors

@app.route('/api/delete_pulse_plot_test', methods=['DELETE'])
def delete_pulse_plot_test():
    """Delete a pulse plot test"""
    try:
        data = request.json
        swimmer_id = data.get('swimmer_id')
        test_date = data.get('test_date')
        stroke = data.get('stroke')

        if not swimmer_id or not test_date or not stroke:
            return jsonify({
                'success': False,
                'error': 'Missing required parameters'
            }), 400

        from modules.database import get_connection
        conn = get_connection()
        cursor = conn.cursor()

        # Delete from database
        cursor.execute('''
            DELETE FROM pulse_plot_tests 
            WHERE swimmer_id = ? AND test_date = ? AND stroke = ?
        ''', (swimmer_id, test_date, stroke))

        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()

        if deleted_count == 0:
            return jsonify({
                'success': False,
                'error': 'Test not found'
            }), 404

        # Also try to remove from file if it exists
        try:
            swimmer = get_swimmer(swimmer_id)
            if swimmer:
                swimmer_name = swimmer['name'].lower().replace(' ', '_')
                file_path = os.path.join('pulse_plot_data', f"{swimmer_name}.json")

                if os.path.exists(file_path):
                    with open(file_path, 'r') as f:
                        file_data = json.load(f)

                    # Remove matching test from file
                    updated_data = [
                        test for test in file_data 
                        if not (test.get('date') == test_date and test.get('stroke') == stroke)
                    ]

                    with open(file_path, 'w') as f:
                        json.dump(updated_data, f, indent=4)
        except Exception as file_error:
            print(f"Warning: Could not update file: {file_error}")

        return jsonify({
            'success': True,
            'message': 'Test deleted successfully'
        })

    except Exception as e:
        print(f"Error deleting pulse plot test: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# ============================================================================
# EMAIL API
# ============================================================================

def send_email_smtp(to_email, subject, content, from_email=None, from_password=None):
    """Send email using SMTP (supports multiple providers)"""
    try:
        # Use provided values or get from config
        if from_email and from_password:
            sender_email = from_email
            sender_password = from_password
        else:
            from email_config import get_email_config
            sender_email, sender_password = get_email_config()

        # Debug logging (remove sensitive info)
        print(f"🔧 EMAIL DEBUG:")
        print(f"  - EMAIL_USER exists: {bool(os.environ.get('EMAIL_USER'))}")
        print(f"  - EMAIL_PASSWORD exists: {bool(os.environ.get('EMAIL_PASSWORD'))}")

        if sender_email:
            email_parts = sender_email.split('@')
            if len(email_parts) >= 2:
                print(f"  - Sender email: {sender_email[:5]}***@{email_parts[1]}")
            else:
                print(f"  - Sender email: {sender_email[:5]}*** (invalid format)")
        else:
            print(f"  - Sender email: None")

        print(f"  - Has password: {bool(sender_password)}")

        if not sender_email or not sender_password:
            missing = []
            if not sender_email:
                missing.append("EMAIL_USER")
            if not sender_password:
                missing.append("EMAIL_PASSWORD")
            error_msg = f"Missing required environment variables: {', '.join(missing)}. Please add them in the Secrets tool."
            print(f"❌ {error_msg}")
            return False, error_msg

        # Determine SMTP settings based on email provider
        if '@gmail.com' in sender_email:
            smtp_server = "smtp.gmail.com"
            smtp_port = 587
        elif '@outlook.com' in sender_email or '@hotmail.com' in sender_email:
            smtp_server = "smtp-mail.outlook.com"
            smtp_port = 587
        elif '@yahoo.com' in sender_email:
            smtp_server = "smtp.mail.yahoo.com"
            smtp_port = 587
        else:
            # Default to Gmail settings
            smtp_server = "smtp.gmail.com"
            smtp_port = 587

        print(f"  - Using SMTP: {smtp_server}:{smtp_port}")

        # Create message
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = to_email
        msg['Subject'] = subject

        # Add content
        msg.attach(MIMEText(content, 'plain'))

        # Create SMTP session
        print(f"  - Connecting to {smtp_server}...")
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()  # Enable TLS encryption

        print(f"  - Attempting login...")
        server.login(sender_email, sender_password)

        print(f"  - Sending email...")
        # Send email
        text = msg.as_string()
        server.sendmail(sender_email, to_email, text)
        server.quit()

        print(f"✅ Email sent successfully to {to_email}")
        return True, "Email sent successfully"

    except smtplib.SMTPAuthenticationError as e:
        error_msg = f"Authentication failed: {str(e)}. Please check your email and app password."
        print(f"❌ {error_msg}")
        return False, error_msg
    except smtplib.SMTPException as e:
        error_msg = f"SMTP error: {str(e)}"
        print(f"❌ {error_msg}")
        return False, error_msg
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        print(f"❌ {error_msg}")
        return False, error_msg

@app.route('/api/test_email', methods=['POST'])
def test_email_config():
    """Test email configuration"""
    try:
        data = request.json or {}
        test_recipient = data.get('test_email', 'test@example.com')

        # Test sending a simple email
        subject = "Swimming Training System - Email Test"
        content = """
This is a test email from your Swimming Training System.

If you receive this email, your email configuration is working correctly!

System Information:
- Timestamp: """ + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + """
- Application: Swimming Training System
- Status: Email configuration successful

Best regards,
Swimming Training System
        """

        success, message = send_email_smtp(test_recipient, subject, content)

        return jsonify({
            'success': success,
            'message': message,
            'recipient': test_recipient if success else None
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/send_athlete_email', methods=['POST'])
def send_athlete_email():
    """Send athlete profile information via email"""
    try:
        data = request.json
        recipient_email = data.get('recipient_email')
        recipient_name = data.get('recipient_name')
        subject = data.get('subject')
        content = data.get('content')
        athlete_id = data.get('athlete_id')
        athlete_name = data.get('athlete_name')

        if not recipient_email:
            return jsonify({
                'success': False,
                'error': 'Please select a recipient'
            }), 400

        if not subject or not subject.strip():
            return jsonify({
                'success': False,
                'error': 'Please enter a subject'
            }), 400

        if not content or not content.strip():
            return jsonify({
                'success': False,
                'error': 'Email content is empty. Please select information to include.'
            }), 400

        print(f"📧 Attempting to send email:")
        print(f"  - To: {recipient_email}")
        print(f"  - Subject: {subject}")
        print(f"  - Content length: {len(content)} characters")
        print(f"  - Athlete: {athlete_name} (ID: {athlete_id})")

        # Try to send actual email
        email_success, email_message = send_email_smtp(recipient_email, subject, content)

        status = 'sent' if email_success else 'failed'

        # Log email activity
        try:
            from modules.database import get_connection
            conn = get_connection()
            cursor = conn.cursor()

            # Create email_log table if it doesn't exist
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS email_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    athlete_id INTEGER,
                    athlete_name TEXT,
                    recipient_email TEXT,
                    recipient_name TEXT,
                    subject TEXT,
                    content_length INTEGER,
                    sent_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'sent',
                    error_message TEXT
                )
            ''')

            # Add error_message column if it doesn't exist
            try:
                cursor.execute('ALTER TABLE email_log ADD COLUMN error_message TEXT')
            except sqlite3.OperationalError:
                pass  # Column already exists

            # Log the email
            cursor.execute('''
                INSERT INTO email_log 
                (athlete_id, athlete_name, recipient_email, recipient_name, subject, content_length, status, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (athlete_id, athlete_name, recipient_email, recipient_name, subject, len(content), status, None if email_success else email_message))

            conn.commit()
            conn.close()

        except Exception as log_error:
            print(f"Warning: Could not log email activity: {log_error}")

        if email_success:
            print(f"📧 EMAIL SENT SUCCESSFULLY")
            print(f"To: {recipient_email} ({recipient_name})")
            print(f"Subject: {subject}")
            print(f"Athlete: {athlete_name} (ID: {athlete_id})")

            return jsonify({
                'success': True,
                'message': f'Email sent successfully to {recipient_name}',
                'recipient': recipient_email
            })
        else:
            print(f"❌ EMAIL FAILED TO SEND: {email_message}")
            return jsonify({
                'success': False,
                'error': f'Failed to send email: {email_message}',
                'fallback_message': 'Email service not configured. Please set up EMAIL_USER and EMAIL_PASSWORD environment variables.'
            }), 500

    except Exception as e:
        print(f"Error sending email: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/coach_email')
def coach_email_page():
    """Render the coach email page"""
    return render_template('coach_email.html')

@app.route('/api/training_group_athletes/<int:group_id>')
def get_training_group_athletes(group_id):
    """Get all athletes in a specific training group"""
    try:
        from modules.database import get_connection
        conn = get_connection()
        cursor = conn.cursor()

        # Get athletes assigned to this training group
        cursor.execute('''
            SELECT id, name, team, year, grade, swimcloud_id, phone_number, email, style
            FROM swimmers 
            WHERE training_group_id = ?
            ORDER BY name
        ''', (group_id,))

        athletes = []
        for row in cursor.fetchall():
            athlete = {
                'id': row[0],
                'name': row[1],
                'team': row[2],
                'year': row[3],
                'grade': row[4],
                'swimcloud_id': row[5],
                'phone_number': row[6],
                'email': row[7],
                'style': row[8]
            }
            athletes.append(athlete)

        conn.close()
        return jsonify(athletes)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/send_coach_email', methods=['POST'])
def send_coach_email():
    """Send training group report email to coach"""
    try:
        data = request.json
        recipient_email = data.get('recipient_email')
        recipient_name = data.get('recipient_name')
        subject = data.get('subject')
        content = data.get('content')
        athlete_count = data.get('athlete_count', 0)
        group_id = data.get('group_id')

        if not recipient_email:
            return jsonify({
                'success': False,
                'error': 'Please select a coach with an email address'
            }), 400

        if not subject or not subject.strip():
            return jsonify({
                'success': False,
                'error': 'Please enter a subject'
            }), 400

        if not content or not content.strip():
            return jsonify({
                'success': False,
                'error': 'Email content is empty. Please select information to include.'
            }), 400

        print(f"📧 Sending coach email:")
        print(f"  - To: {recipient_email} ({recipient_name})")
        print(f"  - Subject: {subject}")
        print(f"  - Content length: {len(content)} characters")
        print(f"  - Athletes: {athlete_count}")
        print(f"  - Group ID: {group_id}")

        # Send the email
        email_success, email_message = send_email_smtp(recipient_email, subject, content)

        # Log email activity
        try:
            from modules.database import get_connection
            conn = get_connection()
            cursor = conn.cursor()

            # Create coach_email_log table if it doesn't exist
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS coach_email_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id INTEGER,
                    coach_email TEXT,
                    coach_name TEXT,
                    subject TEXT,
                    athlete_count INTEGER,
                    content_length INTEGER,
                    sent_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'sent',
                    error_message TEXT
                )
            ''')

            status = 'sent' if email_success else 'failed'

            cursor.execute('''
                INSERT INTO coach_email_log 
                (group_id, coach_email, coach_name, subject, athlete_count, content_length, status, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (group_id, recipient_email, recipient_name, subject, athlete_count, len(content), status, None if email_success else email_message))

            conn.commit()
            conn.close()

        except Exception as log_error:
            print(f"Warning: Could not log coach email activity: {log_error}")

        if email_success:
            print(f"✅ COACH EMAIL SENT SUCCESSFULLY")
            return jsonify({
                'success': True,
                'message': f'Training group report sent successfully to {recipient_name}',
                'recipient': recipient_email,
                'athlete_count': athlete_count
            })
        else:
            print(f"❌ COACH EMAIL FAILED: {email_message}")
            return jsonify({
                'success': False,
                'error': f'Failed to send email: {email_message}'
            }), 500

    except Exception as e:
        print(f"Error sending coach email: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# ============================================================================
# MISSING ENDPOINTS
# ============================================================================

@app.route('/swimmers')
def swimmers_route():
    """Main swimmers route for backward compatibility"""
    try:
        from modules.database import get_all_swimmers
        show_all = request.args.get('show_all', 'false').lower() == 'true'
        swimmers = get_all_swimmers()

        if show_all:
            # Return JSON for API calls
            return jsonify(swimmers)
        else:
            # Redirect to main swimmers page
            return redirect('/api/swimmers')

    except Exception as e:
        print('Error in swimmers route:', e)
        return jsonify({"error": str(e)}), 500

@app.route('/all_times')
def all_times():
    """Get all swimmer times (placeholder endpoint)"""
    try:
        # This endpoint might be called by some JavaScript
        # Return empty response for now
        return jsonify([])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================================================
# DEBUG ENDPOINTS
# ============================================================================

@app.route('/api/debug/routes')
def debug_routes():
    """Debug endpoint to list all available routes"""
    routes = []
    for rule in app.url_map.iter_rules():
        routes.append({
            'endpoint': rule.endpoint,
            'methods': list(rule.methods),
            'rule': str(rule)
        })
    return jsonify(routes)

@app.route('/api/test_database')
def test_database():
    """Test database connection and swimmer count"""
    try:
        from modules.database import get_connection, get_all_swimmers

        # Test basic connection
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM swimmers")
        count = cursor.fetchone()[0]
        conn.close()

        # Test get_all_swimmers function
        swimmers = get_all_swimmers()

        return jsonify({
            "success": True,
            "database_connected": True,
            "total_swimmers_in_db": count,
            "swimmers_returned_by_api": len(swimmers),
            "sample_swimmers": swimmers[:3] if swimmers else [],
            "message": f"Database connection successful. Found {count} swimmers in database, API returned {len(swimmers)} swimmers."
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "database_connected": False,
            "error": str(e),
            "message": "Database connection failed"
        }), 500

# ============================================================================
# MAIN APPLICATION
# ============================================================================

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)