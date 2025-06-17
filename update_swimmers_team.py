
import sqlite3
import os

def update_swimmers_team():
    """Update all swimmers to be assigned to MTRO team"""
    db_path = os.path.join(os.path.dirname(__file__), 'swimmers.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # First, ensure the MTRO team exists
        cursor.execute('''
            INSERT OR IGNORE INTO teams (team_name, team_code, access_password, coach_name, contact_email)
            VALUES (?, ?, ?, ?, ?)
        ''', ('Metroplex Aquatics', 'MTRO', None, 'Coach', 'coach@metroplex.com'))
        
        # Get the team ID
        cursor.execute('SELECT id FROM teams WHERE team_code = ?', ('MTRO',))
        team_result = cursor.fetchone()
        
        if not team_result:
            print("Error: Could not create or find MTRO team")
            return False
            
        team_id = team_result[0]
        print(f"Found MTRO team with ID: {team_id}")

        # Update all swimmers to have the MTRO team
        cursor.execute('''
            UPDATE swimmers 
            SET team = 'Metroplex Aquatics', team_id = ?
            WHERE team IS NULL OR team = '' OR team_id IS NULL
        ''', (team_id,))
        
        updated_count = cursor.rowcount
        print(f"Updated {updated_count} swimmers to MTRO team")

        # Also update any swimmers that might have different team values
        cursor.execute('''
            UPDATE swimmers 
            SET team = 'Metroplex Aquatics', team_id = ?
        ''', (team_id,))
        
        total_updated = cursor.rowcount
        print(f"Total swimmers updated to MTRO team: {total_updated}")

        # Verify the update
        cursor.execute('SELECT COUNT(*) FROM swimmers WHERE team_id = ?', (team_id,))
        count_result = cursor.fetchone()
        swimmer_count = count_result[0] if count_result else 0
        
        print(f"Total swimmers now assigned to MTRO: {swimmer_count}")

        # Show sample of updated swimmers
        cursor.execute('SELECT id, name, team, team_id FROM swimmers WHERE team_id = ? LIMIT 5', (team_id,))
        sample_swimmers = cursor.fetchall()
        
        print("\nSample swimmers in MTRO team:")
        for swimmer in sample_swimmers:
            print(f"  ID: {swimmer[0]}, Name: {swimmer[1]}, Team: {swimmer[2]}, Team ID: {swimmer[3]}")

        conn.commit()
        return True

    except Exception as e:
        conn.rollback()
        print(f"Error updating swimmers: {str(e)}")
        return False
    finally:
        conn.close()

if __name__ == "__main__":
    success = update_swimmers_team()
    if success:
        print("\nSwimmers successfully updated to MTRO team!")
    else:
        print("\nFailed to update swimmers to MTRO team!")
