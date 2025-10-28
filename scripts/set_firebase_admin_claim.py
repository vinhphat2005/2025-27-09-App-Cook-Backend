"""
Set Firebase custom claim 'admin' for a user UID.

Usage:
  python set_firebase_admin_claim.py --uid <firebase-uid> --admin true
  python set_firebase_admin_claim.py --uid <firebase-uid> --admin false
  python set_firebase_admin_claim.py --email user@example.com --admin true

Requires Firebase Admin SDK credentials configured (APPLICATION_DEFAULT or service account)
"""
import argparse
import firebase_admin
from firebase_admin import credentials, auth
from firebase_admin.exceptions import FirebaseError
from dotenv import load_dotenv
import os
import sys
from datetime import datetime
from typing import Optional

load_dotenv()

# ==================== LOGGING ====================

def log_audit(message: str, level: str = "INFO"):
    """Log to audit trail with timestamp"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] [{level}] {message}"
    print(log_entry)
    
    # Append to audit log file
    try:
        log_dir = os.path.join(os.path.dirname(__file__), "logs")
        os.makedirs(log_dir, exist_ok=True)
        
        log_file = os.path.join(log_dir, "admin_claims_audit.log")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(log_entry + "\n")
    except Exception as e:
        print(f"⚠️  Failed to write audit log: {e}")


# ==================== HELPER FUNCTIONS ====================

def get_user_by_uid(uid: str) -> Optional[auth.UserRecord]:
    """Get Firebase user by UID with error handling"""
    try:
        user = auth.get_user(uid)
        return user
    except auth.UserNotFoundError:
        log_audit(f"User not found with UID: {uid}", "ERROR")
        return None
    except FirebaseError as e:
        log_audit(f"Firebase error getting user {uid}: {e}", "ERROR")
        return None
    except Exception as e:
        log_audit(f"Unexpected error getting user {uid}: {e}", "ERROR")
        return None


def get_user_by_email(email: str) -> Optional[auth.UserRecord]:
    """Get Firebase user by email with error handling"""
    try:
        user = auth.get_user_by_email(email)
        return user
    except auth.UserNotFoundError:
        log_audit(f"User not found with email: {email}", "ERROR")
        return None
    except FirebaseError as e:
        log_audit(f"Firebase error getting user {email}: {e}", "ERROR")
        return None
    except Exception as e:
        log_audit(f"Unexpected error getting user {email}: {e}", "ERROR")
        return None


def display_user_info(user: auth.UserRecord):
    """Display user information for confirmation"""
    print("\n" + "="*60)
    print("📋 USER INFORMATION")
    print("="*60)
    print(f"UID:           {user.uid}")
    print(f"Email:         {user.email or 'N/A'}")
    print(f"Display Name:  {user.display_name or 'N/A'}")
    print(f"Email Verified: {user.email_verified}")
    print(f"Disabled:      {user.disabled}")
    print(f"Created:       {datetime.fromtimestamp(user.user_metadata.creation_timestamp / 1000)}")
    
    # Show current custom claims
    current_claims = user.custom_claims or {}
    print(f"\nCurrent Claims: {current_claims}")
    print(f"Current Admin:  {current_claims.get('admin', False)}")
    print("="*60 + "\n")


def confirm_action(user: auth.UserRecord, is_admin: bool) -> bool:
    """Prompt user for confirmation before setting admin claim"""
    action = "GRANT" if is_admin else "REVOKE"
    print(f"\n⚠️  WARNING: You are about to {action} admin privileges!")
    print(f"User: {user.email or user.uid}")
    print(f"Action: Set admin = {is_admin}")
    
    response = input("\n❓ Are you sure? Type 'yes' to confirm: ").strip().lower()
    return response == "yes"


# ==================== MAIN SCRIPT ====================

def main():
    parser = argparse.ArgumentParser(
        description="Set Firebase admin custom claim for a user",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python set_firebase_admin_claim.py --uid abc123xyz --admin true
  python set_firebase_admin_claim.py --email admin@example.com --admin true
  python set_firebase_admin_claim.py --uid abc123xyz --admin false --skip-confirm
        """
    )
    
    # User identification (either uid or email required)
    user_group = parser.add_mutually_exclusive_group(required=True)
    user_group.add_argument("--uid", help="Firebase UID of the user")
    user_group.add_argument("--email", help="Email of the user")
    
    # Admin flag
    parser.add_argument(
        "--admin", 
        choices=["true", "false"], 
        default="true",
        help="Set admin claim to true or false (default: true)"
    )
    
    # Skip confirmation (dangerous!)
    parser.add_argument(
        "--skip-confirm",
        action="store_true",
        help="Skip confirmation prompt (use with caution!)"
    )
    
    args = parser.parse_args()
    
    # ==================== INITIALIZE FIREBASE ====================
    
    log_audit("Starting admin claim modification script")
    
    if not firebase_admin._apps:
        try:
            cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            if not cred_path:
                print("❌ Error: GOOGLE_APPLICATION_CREDENTIALS not set in .env")
                log_audit("Missing GOOGLE_APPLICATION_CREDENTIALS", "ERROR")
                sys.exit(1)
            
            if not os.path.exists(cred_path):
                print(f"❌ Error: Service account file not found: {cred_path}")
                log_audit(f"Service account file not found: {cred_path}", "ERROR")
                sys.exit(1)
            
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
            log_audit("Firebase Admin SDK initialized successfully")
            
        except Exception as e:
            print(f"❌ Error initializing Firebase: {e}")
            log_audit(f"Failed to initialize Firebase: {e}", "ERROR")
            sys.exit(1)
    
    # ==================== GET USER ====================
    
    if args.uid:
        print(f"🔍 Looking up user by UID: {args.uid}")
        user = get_user_by_uid(args.uid)
    else:
        print(f"🔍 Looking up user by email: {args.email}")
        user = get_user_by_email(args.email)
    
    if not user:
        print("\n❌ Error: User not found. Please check UID/email and try again.")
        sys.exit(1)
    
    print("✅ User found!")
    
    # ==================== DISPLAY USER INFO ====================
    
    display_user_info(user)
    
    # ==================== CONFIRM ACTION ====================
    
    is_admin = args.admin == "true"
    
    if not args.skip_confirm:
        if not confirm_action(user, is_admin):
            print("\n🚫 Operation cancelled by user.")
            log_audit(f"Operation cancelled - User: {user.email or user.uid}", "INFO")
            sys.exit(0)
    else:
        log_audit("⚠️  Confirmation skipped (--skip-confirm flag used)", "WARNING")
    
    # ==================== SET CUSTOM CLAIMS ====================
    
    try:
        print(f"\n⚙️  Setting admin claim to {is_admin}...")
        
        # Get existing claims and update admin flag
        existing_claims = user.custom_claims or {}
        new_claims = {**existing_claims, "admin": is_admin}
        
        auth.set_custom_user_claims(user.uid, new_claims)
        
        # Verify the change
        updated_user = auth.get_user(user.uid)
        actual_admin = updated_user.custom_claims.get("admin", False)
        
        if actual_admin == is_admin:
            print(f"\n✅ SUCCESS! Admin claim set to {is_admin}")
            print(f"User: {user.email or user.uid}")
            print(f"New claims: {updated_user.custom_claims}")
            
            log_audit(
                f"Admin claim successfully set - User: {user.email or user.uid}, "
                f"UID: {user.uid}, Admin: {is_admin}",
                "SUCCESS"
            )
            
            print("\n💡 Note: User must sign out and sign in again for changes to take effect.")
            
        else:
            print(f"\n⚠️  Warning: Claim was set but verification failed.")
            print(f"Expected admin={is_admin}, got admin={actual_admin}")
            log_audit(
                f"Claim verification mismatch - User: {user.uid}, "
                f"Expected: {is_admin}, Got: {actual_admin}",
                "WARNING"
            )
            
    except auth.UserNotFoundError:
        print(f"\n❌ Error: User no longer exists: {user.uid}")
        log_audit(f"User not found when setting claims: {user.uid}", "ERROR")
        sys.exit(1)
        
    except FirebaseError as e:
        print(f"\n❌ Firebase Error: {e}")
        log_audit(f"Firebase error setting claims for {user.uid}: {e}", "ERROR")
        sys.exit(1)
        
    except Exception as e:
        print(f"\n❌ Unexpected Error: {e}")
        log_audit(f"Unexpected error setting claims for {user.uid}: {e}", "ERROR")
        sys.exit(1)


if __name__ == "__main__":
    main()
