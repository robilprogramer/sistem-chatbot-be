"""
Scheduler - Background Jobs untuk Sync & Cleanup
================================================
Menggunakan APScheduler untuk:
1. Auto-sync ke PostgreSQL setiap X menit
2. Cleanup expired drafts
3. Health check

Install: pip install apscheduler
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SyncScheduler:
    """
    Scheduler untuk background jobs
    """
    
    def __init__(self, use_async: bool = False):
        """
        Initialize scheduler
        
        Args:
            use_async: True untuk asyncio scheduler (FastAPI), False untuk background
        """
        if use_async:
            self.scheduler = AsyncIOScheduler()
        else:
            self.scheduler = BackgroundScheduler()
        
        self.is_running = False
    
    def start(self):
        """Start scheduler"""
        if not self.is_running:
            self.scheduler.start()
            self.is_running = True
            logger.info("✅ Scheduler started")
    
    def stop(self):
        """Stop scheduler"""
        if self.is_running:
            self.scheduler.shutdown()
            self.is_running = False
            logger.info("🛑 Scheduler stopped")
    
    def add_sync_job(self, interval_minutes: int = 5):
        """
        Add job to sync SQLite to PostgreSQL
        
        Args:
            interval_minutes: Sync interval in minutes
        """
        self.scheduler.add_job(
            func=self._run_sync,
            trigger=IntervalTrigger(minutes=interval_minutes),
            id="sync_to_postgres",
            name="Sync SQLite to PostgreSQL",
            replace_existing=True
        )
        logger.info(f"📅 Added sync job: every {interval_minutes} minutes")
    
    def add_cleanup_job(self, hour: int = 2, minute: int = 0):
        """
        Add job to cleanup expired drafts (daily at specified time)
        
        Args:
            hour: Hour to run (0-23)
            minute: Minute to run (0-59)
        """
        self.scheduler.add_job(
            func=self._run_cleanup,
            trigger=CronTrigger(hour=hour, minute=minute),
            id="cleanup_drafts",
            name="Cleanup expired drafts",
            replace_existing=True
        )
        logger.info(f"📅 Added cleanup job: daily at {hour:02d}:{minute:02d}")
    
    def add_immediate_sync_job(self, registration_number: str):
        """
        Add one-time job to sync specific registration immediately
        Used after registration confirmation
        """
        self.scheduler.add_job(
            func=self._run_single_sync,
            args=[registration_number],
            id=f"sync_{registration_number}",
            name=f"Sync {registration_number}",
            replace_existing=True
        )
        logger.info(f"📅 Added immediate sync job for: {registration_number}")
    
    # =========================================================================
    # JOB FUNCTIONS
    # =========================================================================
    
    def _run_sync(self):
        """Execute sync job"""
        try:
            logger.info(f"🔄 Starting scheduled sync at {datetime.now()}")
            
            from app.sync_service import get_sync_service
            service = get_sync_service()
            service.init_postgres_tables()
            report = service.sync_all_pending()
            
            logger.info(f"✅ Sync completed: {report['registrations_synced']} registrations, {report['conversations_synced']} conversations")
            
            if report.get('errors'):
                for err in report['errors']:
                    logger.error(f"❌ Sync error: {err}")
            
        except Exception as e:
            logger.error(f"❌ Sync job failed: {str(e)}")
    
    def _run_single_sync(self, registration_number: str):
        """Execute single registration sync"""
        try:
            logger.info(f"🔄 Syncing registration: {registration_number}")
            
            from app.sync_service import get_sync_service
            service = get_sync_service()
            service.init_postgres_tables()
            success, message = service.sync_registration(registration_number)
            
            if success:
                logger.info(f"✅ Synced: {registration_number}")
            else:
                logger.error(f"❌ Failed to sync {registration_number}: {message}")
            
        except Exception as e:
            logger.error(f"❌ Single sync failed: {str(e)}")
    
    def _run_cleanup(self):
        """Execute cleanup job"""
        try:
            logger.info(f"🧹 Starting cleanup at {datetime.now()}")
            
            from app.database import get_db_manager
            db = get_db_manager()
            deleted = db.cleanup_expired_drafts()
            
            logger.info(f"✅ Cleanup completed: {deleted} expired drafts removed")
            
        except Exception as e:
            logger.error(f"❌ Cleanup job failed: {str(e)}")
    
    def get_jobs(self):
        """Get list of scheduled jobs"""
        return [
            {
                "id": job.id,
                "name": job.name,
                "next_run": str(job.next_run_time),
                "trigger": str(job.trigger)
            }
            for job in self.scheduler.get_jobs()
        ]


# =========================================================================
# SINGLETON
# =========================================================================

_scheduler: SyncScheduler = None


def get_scheduler(use_async: bool = False) -> SyncScheduler:
    """Get or create scheduler instance"""
    global _scheduler
    if _scheduler is None:
        _scheduler = SyncScheduler(use_async=use_async)
    return _scheduler


def init_scheduler(sync_interval: int = 5, cleanup_hour: int = 2):
    """
    Initialize and start scheduler with default jobs
    
    Args:
        sync_interval: Minutes between syncs
        cleanup_hour: Hour to run daily cleanup
    """
    scheduler = get_scheduler(use_async=True)
    scheduler.add_sync_job(interval_minutes=sync_interval)
    scheduler.add_cleanup_job(hour=cleanup_hour)
    scheduler.start()
    return scheduler


def schedule_immediate_sync(registration_number: str):
    """Schedule immediate sync for a registration"""
    scheduler = get_scheduler()
    scheduler.add_immediate_sync_job(registration_number)


# =========================================================================
# FASTAPI INTEGRATION
# =========================================================================

def setup_scheduler_for_fastapi(app):
    """
    Setup scheduler with FastAPI lifespan
    
    Usage in main.py:
        from app.scheduler import setup_scheduler_for_fastapi
        setup_scheduler_for_fastapi(app)
    """
    from contextlib import asynccontextmanager
    
    @asynccontextmanager
    async def lifespan(app):
        # Startup
        scheduler = init_scheduler(sync_interval=5, cleanup_hour=2)
        logger.info("🚀 Scheduler initialized with FastAPI")
        yield
        # Shutdown
        scheduler.stop()
        logger.info("👋 Scheduler stopped")
    
    app.router.lifespan_context = lifespan


# =========================================================================
# CLI
# =========================================================================

if __name__ == "__main__":
    import sys
    import time
    
    if len(sys.argv) < 2:
        print("""
Usage:
    python scheduler.py start           - Start scheduler with default jobs
    python scheduler.py sync-now        - Run sync immediately
    python scheduler.py cleanup-now     - Run cleanup immediately
    python scheduler.py jobs            - List scheduled jobs
        """)
        sys.exit(0)
    
    command = sys.argv[1]
    
    if command == "start":
        print("🚀 Starting scheduler...")
        scheduler = get_scheduler(use_async=False)
        scheduler.add_sync_job(interval_minutes=5)
        scheduler.add_cleanup_job(hour=2)
        scheduler.start()
        
        print("✅ Scheduler running. Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            scheduler.stop()
            print("\n👋 Scheduler stopped")
    
    elif command == "sync-now":
        print("🔄 Running sync now...")
        scheduler = SyncScheduler()
        scheduler._run_sync()
    
    elif command == "cleanup-now":
        print("🧹 Running cleanup now...")
        scheduler = SyncScheduler()
        scheduler._run_cleanup()
    
    elif command == "jobs":
        scheduler = get_scheduler()
        scheduler.add_sync_job(interval_minutes=5)
        scheduler.add_cleanup_job(hour=2)
        
        print("\n📅 SCHEDULED JOBS")
        print("=" * 50)
        for job in scheduler.get_jobs():
            print(f"ID: {job['id']}")
            print(f"Name: {job['name']}")
            print(f"Trigger: {job['trigger']}")
            print("-" * 50)