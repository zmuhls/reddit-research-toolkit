# Reddit Scraper Optimization Guide

## Current Performance Analysis for r/twinpeaks

### Issues Identified

**Problem 1: Multiple Competing Processes**
- Two scraper instances were running simultaneously
- Both hitting the same Reddit API endpoints
- Causing rate limit penalties and doubled wait times

**Problem 2: Inefficient Rate Limiting**
The scraper has multiple sleep delays that compound:
```python
# After each user processed
time.sleep(1.5)  # content_extraction rate limit

# For EACH submission checked (even if not from target subreddit)
time.sleep(0.1)

# For EACH comment checked (even if not from target subreddit)
time.sleep(0.1)
```

**Problem 3: No Limits on User Content Retrieval**
```python
user.submissions.new(limit=None)  # Fetches ALL submissions
user.comments.new(limit=None)     # Fetches ALL comments
```

For users with 10,000+ posts/comments, this can take 15-20 minutes PER USER.

### Current Stats (After 14+ Hours)
- **Total Users:** 5,650 discovered
- **Processed:** 772 (13.7%)
- **Pending:** 4,878 (86.3%)
- **Content Collected:** 1,180 posts, 17,306 comments
- **Estimated Time to Complete:** ~12 days at current rate

---

## Optimization Strategy

### Option 1: Quick Fix - Reduce Sleep Times (2-3x faster)

Edit the rate_limits in your configuration:

```python
'rate_limits': {
    'user_discovery': 0.5,        # Reduced from 1.0
    'content_extraction': 0.5,    # Reduced from 1.5
    'comment_expansion': 1.0,     # Reduced from 2.0
    'batch_processing': 1.0,      # Reduced from 2.0
    'rate_limit_backoff': 60.0
}
```

**Estimated completion time:** ~4-5 days

### Option 2: Aggressive Optimization - Limit User Content (10-20x faster)

Modify `core/reddit_scraper.py` to limit content per user:

```python
# Line 403 - Limit submissions
for submission in user.submissions.new(limit=100):  # Was limit=None

# Line 413 - Limit comments
for comment in user.comments.new(limit=1000):  # Was limit=None
```

**Trade-off:** You'll miss older content from prolific users
**Estimated completion time:** ~12-24 hours

### Option 3: Smart Sampling (Recommended for large datasets)

Only process a sample of users:

```bash
python tools/cli.py scrape \
    --subreddit twinpeaks \
    --max-posts 100 \
    --batch-size 10 \
    --max-users 1000  # Process only 1000 users
```

**Trade-off:** Smaller but more manageable dataset
**Estimated completion time:** ~6-8 hours for 1000 users

### Option 4: Parallel Processing (Most Efficient)

Split the user list and run multiple scrapers with different user ranges:

```bash
# Terminal 1 - Users 1-1000
python tools/cli.py scrape --subreddit twinpeaks --user-range 0-1000

# Terminal 2 - Users 1001-2000
python tools/cli.py scrape --subreddit twinpeaks --user-range 1001-2000
```

**Note:** Would require code modifications to support user-range parameter

---

## Recommended Action Plan

### For r/twinpeaks (Current Scrape)

**Option A: Continue with Optimizations**
1. Apply Option 2 optimizations (limit user content)
2. Reduce rate limits (Option 1)
3. Resume from checkpoint
4. **Estimated time:** 12-24 hours

**Option B: Fresh Start with Smart Settings**
1. Delete current checkpoint and database
2. Use Option 3 (sample 1500 users)
3. Get results in 8-10 hours
4. Better for analysis and testing

### Quick Resume Script

```bash
#!/bin/bash
# Save as: scripts/resume_twinpeaks_optimized.sh

python tools/cli.py scrape \
    --subreddit twinpeaks \
    --max-posts 100 \
    --batch-size 15 \
    --max-users 2000 \
    --time-filter all
```

Make executable: `chmod +x scripts/resume_twinpeaks_optimized.sh`

---

## Code Modifications for Maximum Speed

### Edit: core/reddit_scraper.py

**1. Reduce submission/comment iteration delays (lines 407, 417):**
```python
# Change from:
time.sleep(0.1)

# To:
time.sleep(0.01)  # 10x faster
```

**2. Add content limits (lines 403, 413):**
```python
# Submissions
for submission in user.submissions.new(limit=100):  # Add limit

# Comments
for comment in user.comments.new(limit=1000):  # Add limit
```

**3. Optimize batch processing (line 372):**
```python
# Change from:
time.sleep(self.rate_limits['batch_processing'])

# To:
time.sleep(0.5)  # Fixed 0.5 second delay
```

### Expected Results After Modifications

- **Processing speed:** 15-30 seconds per user (was 3-5 minutes)
- **Total time for 5,650 users:** ~24-48 hours (was ~12 days)
- **Trade-off:** May miss some older content from very active users

---

## Monitoring Progress

```bash
# Check current status
sqlite3 databases/twinpeaks_data.db "
SELECT
    COUNT(*) as total_users,
    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
    SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
    printf('%.1f%%',
        CAST(SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*) * 100
    ) as percent_complete
FROM users;
"

# Check content collected
sqlite3 databases/twinpeaks_data.db "
SELECT
    (SELECT COUNT(*) FROM submissions) as posts,
    (SELECT COUNT(*) FROM comments) as comments;
"

# Watch log in real-time
tail -f logs/twinpeaks.log
```

---

## Next Steps

1. **Decision Point:** Do you want to:
   - A) Resume current scrape with optimizations?
   - B) Start fresh with smarter limits?
   - C) Continue as-is and wait 10+ more days?

2. **If Resume (A):** I can apply the code modifications now

3. **If Fresh Start (B):** I can create an optimized launch script

Let me know which approach you prefer!
