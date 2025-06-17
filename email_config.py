
import os

def get_email_config():
    """Get email configuration from environment or config file"""
    
    # Try environment variables first (Secrets tool)
    email_user = os.environ.get('EMAIL_USER')
    email_password = os.environ.get('EMAIL_PASSWORD')
    
    if email_user and email_password:
        return email_user, email_password
    
    # Fallback: try reading from a local config file
    try:
        with open('.email_config', 'r') as f:
            lines = f.read().strip().split('\n')
            if len(lines) >= 2:
                return lines[0].strip(), lines[1].strip()
    except FileNotFoundError:
        pass
    
    return None, None

# Usage example:
if __name__ == "__main__":
    user, password = get_email_config()
    print(f"Email user found: {bool(user)}")
    print(f"Email password found: {bool(password)}")
