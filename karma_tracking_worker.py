"""
EchoMind Karma Tracking Worker
Monitors Reddit account karma, syncs daily, detects shadowbans
"""

import os
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional
import praw
from celery import Celery
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import logging

# Setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Celery setup
celery_app = Celery('karma_tracking', broker=os.getenv('CELERY_BROKER_URL'))

# Database setup
DATABASE_URL = os.getenv('DATABASE_URL')
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

# Reddit API setup
reddit = praw.Reddit(
    client_id=os.getenv('REDDIT_CLIENT_ID'),
    client_secret=os.getenv('REDDIT_CLIENT_SECRET'),
    user_agent='EchoMind/1.0'
)


# ============================================================================
# DAILY KARMA SYNC
# ============================================================================

@celery_app.task(name='sync_all_account_karma')
def sync_all_account_karma():
    """
    Sync karma for all active Reddit accounts
    Runs daily at 2 AM
    """
    logger.info("Starting daily karma sync for all accounts")
    
    db = SessionLocal()
    try:
        # Get all active accounts
        result = db.execute(text("""
            SELECT account_id, reddit_username, client_id
            FROM reddit_accounts
            WHERE account_status = 'active'
            AND (last_karma_sync IS NULL OR last_karma_sync < NOW() - INTERVAL '20 hours')
        """))
        
        accounts = result.fetchall()
        logger.info(f"Found {len(accounts)} accounts to sync")
        
        success_count = 0
        error_count = 0
        
        for account in accounts:
            try:
                sync_account_karma(account.account_id, account.reddit_username, db)
                success_count += 1
            except Exception as e:
                logger.error(f"Error syncing {account.reddit_username}: {e}")
                error_count += 1
                
                # Update error tracking
                db.execute(text("""
                    UPDATE reddit_accounts
                    SET sync_error_count = sync_error_count + 1,
                        last_sync_error = :error
                    WHERE account_id = :account_id
                """), {"account_id": account.account_id, "error": str(e)})
                db.commit()
        
        logger.info(f"Karma sync complete: {success_count} success, {error_count} errors")
        
        # Record daily snapshots
        record_daily_snapshots(db)
        
        return {
            "success_count": success_count,
            "error_count": error_count,
            "total": len(accounts)
        }
        
    finally:
        db.close()


def sync_account_karma(account_id: str, username: str, db):
    """
    Sync karma and stats for a single Reddit account
    """
    logger.info(f"Syncing karma for {username}")
    
    try:
        # Fetch from Reddit API
        redditor = reddit.redditor(username)
        
        # Check if account exists and is accessible
        try:
            _ = redditor.id  # This will fail if user doesn't exist or is suspended
        except Exception:
            logger.warning(f"Account {username} is suspended or doesn't exist")
            db.execute(text("""
                UPDATE reddit_accounts
                SET is_suspended = true,
                    account_status = 'suspended',
                    last_health_check = NOW()
                WHERE account_id = :account_id
            """), {"account_id": account_id})
            db.commit()
            return
        
        # Get karma stats
        total_karma = redditor.link_karma + redditor.comment_karma
        
        # Get recent activity stats
        recent_posts = list(redditor.submissions.new(limit=100))
        recent_comments = list(redditor.comments.new(limit=100))
        
        # Calculate averages
        avg_post_score = sum(p.score for p in recent_posts) / max(len(recent_posts), 1)
        avg_comment_score = sum(c.score for c in recent_comments) / max(len(recent_comments), 1)
        
        # Find top scores
        top_post_score = max([p.score for p in recent_posts], default=0)
        top_comment_score = max([c.score for c in recent_comments], default=0)
        
        # Get subreddit activity
        subreddits_active = list(set(
            [p.subreddit.display_name for p in recent_posts] +
            [c.subreddit.display_name for c in recent_comments]
        ))
        
        # Calculate account age
        created_utc = datetime.fromtimestamp(redditor.created_utc)
        account_age_days = (datetime.now() - created_utc).days
        
        # Update database
        db.execute(text("""
            UPDATE reddit_accounts
            SET 
                reddit_user_id = :user_id,
                total_karma = :total_karma,
                post_karma = :post_karma,
                comment_karma = :comment_karma,
                awardee_karma = :awardee_karma,
                awarder_karma = :awarder_karma,
                
                account_age_days = :account_age_days,
                is_suspended = false,
                is_verified = :is_verified,
                has_verified_email = :has_verified_email,
                
                total_posts_count = :posts_count,
                total_comments_count = :comments_count,
                subreddits_active_in = :subreddits,
                
                avg_post_score = :avg_post_score,
                avg_comment_score = :avg_comment_score,
                top_post_score = :top_post_score,
                top_comment_score = :top_comment_score,
                
                last_karma_sync = NOW(),
                last_activity_sync = NOW(),
                last_health_check = NOW(),
                sync_error_count = 0,
                updated_at = NOW()
                
            WHERE account_id = :account_id
        """), {
            "account_id": account_id,
            "user_id": redditor.id,
            "total_karma": total_karma,
            "post_karma": redditor.link_karma,
            "comment_karma": redditor.comment_karma,
            "awardee_karma": redditor.awardee_karma if hasattr(redditor, 'awardee_karma') else 0,
            "awarder_karma": redditor.awarder_karma if hasattr(redditor, 'awarder_karma') else 0,
            "account_age_days": account_age_days,
            "is_verified": redditor.is_employee or redditor.is_gold,
            "has_verified_email": redditor.has_verified_email,
            "posts_count": len(recent_posts),
            "comments_count": len(recent_comments),
            "subreddits": subreddits_active,
            "avg_post_score": round(avg_post_score, 2),
            "avg_comment_score": round(avg_comment_score, 2),
            "top_post_score": top_post_score,
            "top_comment_score": top_comment_score
        })
        
        db.commit()
        logger.info(f"✅ Synced {username}: {total_karma} karma")
        
        # Check for shadowban
        check_shadowban_status(account_id, username, db)
        
    except Exception as e:
        logger.error(f"Error fetching data for {username}: {e}")
        raise


def record_daily_snapshots(db):
    """
    Record daily karma snapshots for all accounts
    """
    logger.info("Recording daily karma snapshots")
    
    try:
        result = db.execute(text("""
            SELECT record_daily_karma_snapshot()
        """))
        
        count = result.scalar()
        logger.info(f"✅ Recorded {count} karma snapshots")
        db.commit()
        
    except Exception as e:
        logger.error(f"Error recording snapshots: {e}")
        db.rollback()


# ============================================================================
# SHADOWBAN DETECTION
# ============================================================================

@celery_app.task(name='check_all_shadowbans')
def check_all_shadowbans():
    """
    Check shadowban status for all accounts
    Runs weekly
    """
    logger.info("Starting shadowban check for all accounts")
    
    db = SessionLocal()
    try:
        result = db.execute(text("""
            SELECT account_id, reddit_username
            FROM reddit_accounts
            WHERE account_status = 'active'
            AND (shadowban_check_date IS NULL OR shadowban_check_date < CURRENT_DATE - INTERVAL '7 days')
        """))
        
        accounts = result.fetchall()
        logger.info(f"Checking {len(accounts)} accounts for shadowban")
        
        for account in accounts:
            try:
                check_shadowban_status(account.account_id, account.reddit_username, db)
            except Exception as e:
                logger.error(f"Error checking shadowban for {account.reddit_username}: {e}")
        
        db.commit()
        
    finally:
        db.close()


def check_shadowban_status(account_id: str, username: str, db):
    """
    Check if account is shadowbanned
    Method: Try to fetch user page, check if accessible
    """
    try:
        redditor = reddit.redditor(username)
        
        # Try to access user's profile
        try:
            # If we can fetch submissions, account is not shadowbanned
            submissions = list(redditor.submissions.new(limit=1))
            is_shadowbanned = False
            
        except Exception:
            # If we get a 404 or forbidden, likely shadowbanned
            is_shadowbanned = True
        
        # Update database
        db.execute(text("""
            UPDATE reddit_accounts
            SET 
                is_shadowbanned = :is_shadowbanned,
                shadowban_check_date = CURRENT_DATE,
                last_health_check = NOW()
            WHERE account_id = :account_id
        """), {
            "account_id": account_id,
            "is_shadowbanned": is_shadowbanned
        })
        
        if is_shadowbanned:
            logger.warning(f"⚠️ Account {username} appears to be shadowbanned!")
        
    except Exception as e:
        logger.error(f"Error checking shadowban for {username}: {e}")


# ============================================================================
# ACTIVITY LOGGING
# ============================================================================

@celery_app.task(name='log_account_activity')
def log_account_activity(account_id: str, username: str):
    """
    Log all recent posts/comments from an account
    For detailed performance tracking
    """
    logger.info(f"Logging activity for {username}")
    
    db = SessionLocal()
    try:
        redditor = reddit.redditor(username)
        
        # Get recent submissions (posts)
        for submission in redditor.submissions.new(limit=50):
            log_submission(account_id, submission, db)
        
        # Get recent comments
        for comment in redditor.comments.new(limit=50):
            log_comment(account_id, comment, db)
        
        db.commit()
        logger.info(f"✅ Logged activity for {username}")
        
    except Exception as e:
        logger.error(f"Error logging activity for {username}: {e}")
        db.rollback()
    finally:
        db.close()


def log_submission(account_id: str, submission, db):
    """Log a Reddit post"""
    try:
        db.execute(text("""
            INSERT INTO reddit_account_activity_log (
                account_id,
                reddit_post_id,
                activity_type,
                subreddit,
                title,
                body,
                permalink,
                score,
                upvote_ratio,
                num_comments,
                is_stickied,
                is_removed,
                posted_at
            ) VALUES (
                :account_id, :post_id, 'post', :subreddit, :title, :body,
                :permalink, :score, :upvote_ratio, :num_comments,
                :is_stickied, :is_removed, :posted_at
            )
            ON CONFLICT (reddit_post_id) DO UPDATE
            SET 
                score = EXCLUDED.score,
                upvote_ratio = EXCLUDED.upvote_ratio,
                num_comments = EXCLUDED.num_comments,
                is_removed = EXCLUDED.is_removed,
                last_updated = NOW()
        """), {
            "account_id": account_id,
            "post_id": submission.id,
            "subreddit": submission.subreddit.display_name,
            "title": submission.title,
            "body": submission.selftext if hasattr(submission, 'selftext') else None,
            "permalink": submission.permalink,
            "score": submission.score,
            "upvote_ratio": submission.upvote_ratio,
            "num_comments": submission.num_comments,
            "is_stickied": submission.stickied,
            "is_removed": submission.removed_by_category is not None,
            "posted_at": datetime.fromtimestamp(submission.created_utc)
        })
    except Exception as e:
        logger.error(f"Error logging submission {submission.id}: {e}")


def log_comment(account_id: str, comment, db):
    """Log a Reddit comment"""
    try:
        db.execute(text("""
            INSERT INTO reddit_account_activity_log (
                account_id,
                reddit_post_id,
                activity_type,
                subreddit,
                body,
                permalink,
                parent_post_id,
                parent_comment_id,
                score,
                is_top_comment,
                is_removed,
                posted_at
            ) VALUES (
                :account_id, :post_id, 'comment', :subreddit, :body,
                :permalink, :parent_post_id, :parent_comment_id, :score,
                :is_top_comment, :is_removed, :posted_at
            )
            ON CONFLICT (reddit_post_id) DO UPDATE
            SET 
                score = EXCLUDED.score,
                is_removed = EXCLUDED.is_removed,
                last_updated = NOW()
        """), {
            "account_id": account_id,
            "post_id": comment.id,
            "subreddit": comment.subreddit.display_name,
            "body": comment.body,
            "permalink": comment.permalink,
            "parent_post_id": comment.parent_id if not comment.is_root else None,
            "parent_comment_id": comment.parent_id if comment.is_root else None,
            "score": comment.score,
            "is_top_comment": comment.is_submitter,
            "is_removed": hasattr(comment, 'removed') and comment.removed,
            "posted_at": datetime.fromtimestamp(comment.created_utc)
        })
    except Exception as e:
        logger.error(f"Error logging comment {comment.id}: {e}")


# ============================================================================
# SCHEDULED TASKS
# ============================================================================

# Daily at 2 AM: Sync all karma
@celery_app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    # Every day at 2 AM
    sender.add_periodic_task(
        crontab(hour=2, minute=0),
        sync_all_account_karma.s(),
        name='daily_karma_sync'
    )
    
    # Every week on Sunday at 3 AM
    sender.add_periodic_task(
        crontab(hour=3, minute=0, day_of_week=0),
        check_all_shadowbans.s(),
        name='weekly_shadowban_check'
    )


if __name__ == '__main__':
    # Test run
    sync_all_account_karma()
