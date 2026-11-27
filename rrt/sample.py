"""Synthetic sample dataset.

Reddit's terms do not allow redistributing real posts, and many students have
no API credentials, so the toolkit ships a generator instead of data. It
invents a small campus community with believable shape: an evening peak, a
weekly rhythm, a start-of-term surge, long-tailed scores, and nested comment
threads. Every row is fabricated and labelled as such.

The generator is deterministic. The same seed produces the same rows on every
machine, so a class can work from identical data.

The companion dashboard carries a copy of this file as src/sample_data.py.
"""

from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple

SUBREDDIT = "SampleCampus"
DEFAULT_SEED = 42
DEFAULT_POSTS = 300

_START = datetime(2026, 7, 1, tzinfo=timezone.utc)
_DAYS = 120
_LOCAL_OFFSET_HOURS = 4  # the invented campus runs on US Eastern daylight time

# Relative activity by local hour (0-23) and by weekday (Monday first).
_HOUR_WEIGHTS = [3, 2, 1, 1, 1, 1, 2, 4, 6, 8, 9, 10, 11, 11, 10, 10, 11, 12, 14, 16, 18, 17, 12, 7]
_WEEKDAY_WEIGHTS = [1.15, 1.2, 1.2, 1.1, 0.85, 0.6, 0.95]

_FLAIRS = [("Question", 35), ("Advice", 20), ("Discussion", 20), ("Rant", 10), ("News", 8), ("Humor", 7)]

_COURSES = ["BIO 101", "CS 111", "ENG 220", "HIST 151", "MATH 201", "PSY 240", "STAT 301", "CHEM 110", "ECON 102", "SOC 205"]
_OFFICES = ["the registrar", "financial aid", "the bursar", "advising", "the tutoring center", "career services", "IT help desk"]
_PLACES = ["the library", "the student center", "the science building", "the quad", "the north cafeteria", "the gym"]
_TOPICS = ["transfer credits", "the waitlist", "a late add", "a course withdrawal", "the payment plan", "work study", "an incomplete grade", "the commute"]

_TITLES = {
    "Question": [
        "Has anyone taken {course} online?",
        "How long does {office} take to respond?",
        "Is {place} open late during finals?",
        "Who do I ask about {topic}?",
        "Can I take {course} and {course2} in the same term?",
        "What is the workload like in {course}?",
        "Does {office} accept walk-ins?",
        "Anyone know when grades for {course} post?",
    ],
    "Advice": [
        "Tips for surviving {course}",
        "What I wish I knew about {topic}",
        "How I got {office} to fix my schedule",
        "Best quiet spots near {place}",
        "A study plan that worked for {course}",
        "Start on {topic} early. Here is why",
    ],
    "Discussion": [
        "Thoughts on the new hours at {place}?",
        "Is {course} worth it as an elective?",
        "How is everyone handling {topic} this term?",
        "What would you change about {office}?",
        "Morning classes or evening classes?",
        "Favorite professor for {course}?",
    ],
    "Rant": [
        "Three weeks waiting on {office}",
        "{place} has no outlets and I am losing it",
        "{topic} is a mess again",
        "Why is {course} only offered at 8am",
        "The elevator in {place} is down. Again",
    ],
    "News": [
        "Registration opens next week",
        "New shuttle schedule posted",
        "{place} closing early on Friday",
        "Update from {office} on {topic}",
        "Tutoring for {course} added on weekends",
    ],
    "Humor": [
        "Me walking into {course} after no sleep",
        "{place} at 2am during finals",
        "The line at {office} right now",
        "POV: you opened the {course} syllabus",
    ],
}

_BODIES = [
    "I looked through the site and could not find a clear rule on this.",
    "Posting here since my advisor is out until next week.",
    "This is my first term, so apologies if it has been asked before.",
    "I work evenings, which limits the sections I can take.",
    "Two people told me two different things and now I am not sure.",
    "Sharing in case it saves someone else the trouble.",
    "Any pointers would help a lot.",
    "I commute about an hour each way, so timing matters.",
    "The deadline is coming up and I would rather not guess.",
    "It took me a full semester to figure this out.",
]

_COMMENTS = [
    "I had the same question last term. Email them and follow up in person.",
    "It depends on the section. Mine was manageable.",
    "Go early. The line is short before 10.",
    "Thanks for posting this, I needed it.",
    "That has not been my experience at all.",
    "Check the academic calendar, the date is listed there.",
    "The tutoring center helped me a lot with that course.",
    "Same thing happened to me. It got sorted out after a week.",
    "You can do both, but the workload adds up fast.",
    "I would wait until after the add/drop period to decide.",
    "This is the most useful thread I have seen here.",
    "Honestly it was fine once I started going to office hours.",
    "They changed the policy this year, so older advice may be off.",
    "Second floor is quieter, especially on weekday mornings.",
    "Did you ever get a reply?",
    "Following. I am in the same spot.",
    "Try calling. Email took two weeks for me.",
    "Can confirm, it worked for me too.",
]

_OP_REPLIES = [
    "Thank you, that clears it up.",
    "I will try that tomorrow and report back.",
    "Update: it worked. Appreciate the help.",
    "Good to know, I had no idea.",
]


def _weighted(rng: random.Random, pairs) -> Any:
    values, weights = zip(*pairs)
    return rng.choices(values, weights=weights, k=1)[0]


def _iso(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _day_weight(day_index: int, weekday: int) -> float:
    """Weekly rhythm plus two surges: the start of term and midterms."""
    weight = _WEEKDAY_WEIGHTS[weekday]
    weight *= 1 + 1.6 * math.exp(-((day_index - 56) ** 2) / (2 * 6 ** 2))   # term starts in late August
    weight *= 1 + 0.9 * math.exp(-((day_index - 105) ** 2) / (2 * 5 ** 2))  # midterms in mid October
    return weight


def generate(n_posts: int = DEFAULT_POSTS, seed: int = DEFAULT_SEED) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Return (posts, comments) as lists of row dictionaries in dataset column names."""
    rng = random.Random(seed)

    users = [f"sample_user_{number:03d}" for number in range(1, 181)]
    user_weights = [1 / (rank ** 0.8) for rank in range(1, len(users) + 1)]

    days = [(_START + timedelta(days=offset)) for offset in range(_DAYS)]
    day_weights = [_day_weight(index, day.weekday()) for index, day in enumerate(days)]

    posts: List[Dict[str, Any]] = []
    comments: List[Dict[str, Any]] = []
    comment_number = 0

    moments = []
    for _ in range(n_posts):
        day = rng.choices(days, weights=day_weights, k=1)[0]
        hour = rng.choices(range(24), weights=_HOUR_WEIGHTS, k=1)[0]
        local = day + timedelta(hours=hour, minutes=rng.randrange(60), seconds=rng.randrange(60))
        moments.append(local + timedelta(hours=_LOCAL_OFFSET_HOURS))
    moments.sort()

    for index, created in enumerate(moments, 1):
        flair = _weighted(rng, _FLAIRS)
        course, course2 = rng.sample(_COURSES, 2)
        title = rng.choice(_TITLES[flair]).format(
            course=course, course2=course2, office=rng.choice(_OFFICES), place=rng.choice(_PLACES), topic=rng.choice(_TOPICS)
        )
        title = title[0].upper() + title[1:]
        author = rng.choices(users, weights=user_weights, k=1)[0]
        is_self = flair not in ("Humor", "News") or rng.random() < 0.3
        post_id = f"sample{index:04d}"

        boost = {"Humor": 1.0, "Rant": 0.5, "News": 0.4}.get(flair, 0.0)
        score = max(0, int(rng.lognormvariate(2.2 + boost, 1.1)) - 1)
        ratio = round(min(0.99, max(0.45, rng.betavariate(9, 1.6))), 2)
        n_comments = min(45, int(rng.lognormvariate(1.0 + 0.25 * math.log1p(score), 0.8)))
        if flair == "Question" and n_comments == 0 and rng.random() < 0.6:
            n_comments = 1

        post_comments: List[Dict[str, Any]] = []
        for _ in range(n_comments):
            comment_number += 1
            comment_id = f"samplec{comment_number:05d}"
            if post_comments and rng.random() > 0.55:
                parent = rng.choice(post_comments)
                depth = min(parent["depth"] + 1, 6)
                parent_id = f"t1_{parent['comment_id']}" if parent["depth"] < 6 else parent["parent_id"]
                earliest = datetime.strptime(parent["created_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            else:
                depth = 0
                parent_id = f"t3_{post_id}"
                earliest = created
            by_op = depth > 0 and rng.random() < 0.18
            commenter = author if by_op else rng.choices(users, weights=user_weights, k=1)[0]
            when = earliest + timedelta(minutes=rng.expovariate(1 / 95) + 1)
            body = rng.choice(_OP_REPLIES if by_op else _COMMENTS)
            post_comments.append(
                {
                    "comment_id": comment_id,
                    "post_id": post_id,
                    "parent_id": parent_id,
                    "subreddit": SUBREDDIT,
                    "author": commenter,
                    "created_utc": _iso(when),
                    "score": int(rng.lognormvariate(0.9, 1.0)) - (2 if rng.random() < 0.08 else 0),
                    "depth": depth,
                    "is_submitter": commenter == author,
                    "stickied": False,
                    "edited": rng.random() < 0.06,
                    "permalink": "",
                    "body": body,
                }
            )
        comments.extend(post_comments)

        posts.append(
            {
                "post_id": post_id,
                "subreddit": SUBREDDIT,
                "title": title,
                "author": author,
                "created_utc": _iso(created),
                "score": score,
                "upvote_ratio": ratio,
                "num_comments": len(post_comments),
                "flair": flair,
                "is_self": is_self,
                "is_video": False,
                "over_18": False,
                "spoiler": False,
                "stickied": False,
                "domain": f"self.{SUBREDDIT}" if is_self else "example.com",
                "url": "" if is_self else f"https://example.com/sample/{post_id}",
                "permalink": "",
                "selftext": " ".join(rng.sample(_BODIES, rng.randint(1, 3))) if is_self else "",
            }
        )

    return posts, comments


def write_sample(root=None, n_posts: int = DEFAULT_POSTS, seed: int = DEFAULT_SEED):
    """Generate the sample and write it as a dataset folder. Returns the folder path."""
    from .datasets import STATUS_COMPLETE, DatasetWriter

    posts, comments = generate(n_posts=n_posts, seed=seed)
    writer = DatasetWriter(
        [SUBREDDIT],
        {"generator": "rrt.sample", "seed": seed, "posts": n_posts},
        root=root,
        source="synthetic",
        label="sample",
        notes="Synthetic practice data. Every post, comment, and username was invented by a program.",
    )
    for post in posts:
        writer.add_post(post)
    for comment in comments:
        writer.add_comment(comment)
    return writer.close(STATUS_COMPLETE)
