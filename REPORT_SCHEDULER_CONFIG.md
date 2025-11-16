# Weekly Report Scheduler Configuration

## Current Status
The weekly report emails are **mentioned** in onboarding communications but the actual scheduler implementation needs to be configured.

## Required Configuration

### Report Schedule
- **Frequency**: Monday & Thursday
- **Time**: 7:00 AM EST
- **Recipients**: All active clients via email/Slack

### Implementation Options

#### Option 1: Celery Beat (Recommended)
Add to `celerybeat-schedule.py` or similar:

```python
from celery.schedules import crontab

app.conf.beat_schedule = {
    'send-weekly-reports-monday': {
        'task': 'workers.report_generator.send_weekly_report',
        'schedule': crontab(day_of_week=1, hour=12, minute=0),  # Monday 7am EST = 12pm UTC
        'args': (),
    },
    'send-weekly-reports-thursday': {
        'task': 'workers.report_generator.send_weekly_report',
        'schedule': crontab(day_of_week=4, hour=12, minute=0),  # Thursday 7am EST = 12pm UTC
        'args': (),
    },
}
```

#### Option 2: APScheduler (Alternative)
Add to `main.py` startup:

```python
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

scheduler = BackgroundScheduler()

# Monday & Thursday at 7am EST (12pm UTC)
scheduler.add_job(
    func=send_weekly_report_to_all_clients,
    trigger=CronTrigger(day_of_week='mon,thu', hour=12, minute=0, timezone='UTC'),
    id='weekly_reports',
    name='Send Weekly Reports',
    replace_existing=True
)

scheduler.start()
```

#### Option 3: Railway Cron Jobs
Create `.railway/cron.json`:

```json
{
  "jobs": [
    {
      "name": "weekly-reports-monday",
      "schedule": "0 12 * * 1",
      "command": "python -m workers.report_generator"
    },
    {
      "name": "weekly-reports-thursday",
      "schedule": "0 12 * * 4",
      "command": "python -m workers.report_generator"
    }
  ]
}
```

### Required Worker: `workers/report_generator.py`

Create a new worker that:
1. Fetches all active clients
2. For each client:
   - Query opportunities discovered in past week
   - Generate AI analysis summary
   - Format email with top opportunities
   - Send via Resend API
3. Log results to database

Example structure:

```python
"""
Weekly Report Generator
Sends Monday/Thursday 7am EST reports to all active clients
"""

async def send_weekly_report_to_all_clients():
    """Send weekly report to all active clients"""
    clients = await fetch_active_clients()
    
    for client in clients:
        try:
            # Get week's opportunities
            opportunities = await fetch_weekly_opportunities(client['client_id'])
            
            # Generate analysis
            analysis = await generate_weekly_analysis(opportunities, client)
            
            # Send email
            await send_report_email(client, opportunities, analysis)
            
            logger.info(f"✅ Report sent to {client['company_name']}")
        except Exception as e:
            logger.error(f"❌ Report failed for {client['company_name']}: {e}")
```

## Timezone Notes
- **User-facing time**: 7:00 AM EST/EDT
- **Server time (UTC)**: 12:00 PM (EST) or 11:00 AM (EDT during daylight saving)
- **Recommendation**: Use UTC time 12:00 and document clearly

## Testing
Before going live:
1. Test report generation with real client data
2. Verify email formatting and content
3. Test timezone conversion (EST/EDT)
4. Confirm Resend API can handle batch sends
5. Add error handling and retry logic

## Email Content
The report should include:
- Week summary (Mon-Sun or Thu-Wed)
- Top 10 opportunities by score
- Priority breakdown (Platinum/Gold/Silver)
- AI-generated strategic insights
- Dashboard link with filters pre-set to this week
- Next steps / action items

## Monitoring
- Log all report sends to database
- Track open rates via Resend webhooks
- Monitor for failures and alert team
- Weekly summary of report performance

---

## Current Implementation Status

✅ **Email templates updated** - Mentions "7am EST" in onboarding
✅ **Notification service** - Can send emails via Resend
❌ **Scheduler** - Not yet configured (needs implementation above)
❌ **Report generator worker** - Needs to be created
❌ **Weekly report endpoint** - Needs to be created for manual testing

## Next Steps
1. Create `workers/report_generator.py` worker
2. Implement one of the scheduling options above
3. Test with The Waite client
4. Deploy to Railway
5. Monitor first few weeks of automated reports
