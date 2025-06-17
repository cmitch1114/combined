
import os

print("Testing secret access:")
print(f"EMAIL_USER exists: {bool(os.environ.get('EMAIL_USER'))}")
print(f"EMAIL_USER value: {os.environ.get('EMAIL_USER', 'NOT FOUND')}")
print(f"EMAIL_PASSWORD exists: {bool(os.environ.get('EMAIL_PASSWORD'))}")

# Show all environment variables that contain 'EMAIL'
print("\nAll EMAIL-related environment variables:")
for key, value in os.environ.items():
    if 'EMAIL' in key.upper():
        print(f"{key}: {value[:3]}*** (showing first 3 chars)")

print(f"\nTotal environment variables: {len(os.environ)}")
