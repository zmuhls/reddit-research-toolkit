# Reddit API access

*Checked on November 27, 2026. Reddit revises these rules often, so confirm dates on the pages linked under [Sources](#sources) before you plan around them.*

Collecting new data with this toolkit requires Reddit API credentials, and Reddit has spent the past year closing the route most tutorials describe. You can no longer create an app at reddit.com/prefs/apps and start collecting. This page explains who can still collect, how, and how everyone else can do the same analysis work without credentials.

## The short version

| Your situation | Your route |
|---|---|
| You hold a client ID and secret that already work | Use them. Run `python main.py setup`. Collect soon, since Reddit ends public API access in March 2027. |
| You are a student in a course | Work from a dataset your instructor shares, or from the built-in sample. You need no credentials. |
| You are a researcher at a university | Apply to Reddit for Researchers. Reddit names it as the one authorized route for research. |
| You have no credentials and no research affiliation | Reddit accepts no new requests. Work from shared or sample data. |

## Timeline

| Date | Change |
|---|---|
| November 11, 2025 | Reddit publishes its Responsible Builder Policy and closes self-service API access. New apps and new tokens require Reddit's approval. |
| September 30, 2026 | Reddit announces the end of its public Data API and of RSS feeds. |
| October 31, 2026 | Reddit stops accepting new requests for public API access. |
| November 13, 2026 | RSS feeds stop. |
| January 12, 2027 | Reddit begins removing API access from apps and users that have not registered with it. |
| March 2027 | Remaining public Data API access ends for all apps and users. Reddit has named no day. |

Two consequences follow for this toolkit.

1. `python main.py scrape` and `tools/cli.py scrape` work only with credentials Reddit already approved, and only until Reddit closes the public API.
2. Every other command works without credentials and will continue to work. A dataset collected today stays usable after March 2027.

## Route 1. You already have working credentials

Reddit's announcements leave existing approved access in place until the removals described above, so credentials that worked before October 31, 2026 should still work.

1. Sign in to Reddit and open <https://www.reddit.com/prefs/apps>.
2. Find your app in the list. The **client ID** is the short string printed under the app's name.
3. Click **edit**. The **secret** is the longer string beside the word "secret".
4. In the toolkit folder, run

   ```bash
   python main.py setup
   ```

   Setup asks for the two values and your Reddit username, saves them in `.env`, and tests them with two real requests. The first request signs in. The second reads one public post, since Reddit can accept a sign-in and still refuse data to an app it has not approved.

5. Register the app with Reddit if you have not. Reddit's developer announcements on r/redditdev describe the process. Registration protects an app from the removals that begin January 12, 2027. It does not extend access past March 2027.

Collect the data you need before the deadline. Each scrape produces a self-contained [dataset folder](DATASET_FORMAT.md) that remains readable in pandas, R, a spreadsheet, and the companion dashboard after API access ends.

Treat the secret as a password.

- `.env` stays on your machine, and Git ignores it.
- Never paste the secret into a chat, an email, a notebook, a screenshot, or a commit.
- Do not hand your credentials to students or collaborators. Reddit ties each app to one account holder, who is responsible for everything the app does. Share datasets, not credentials.
- If a secret leaks, open the app at reddit.com/prefs/apps and delete the app or generate a new secret.

## Route 2. You are a student, or you have no credentials

You can complete every analysis task in this toolkit without credentials.

```bash
python main.py sample            # a synthetic practice dataset, 300 posts and about 2,000 comments
python main.py show              # summary and top posts
python main.py analyze --open    # charts and reports in your browser
```

For real data, ask the person who runs your course or project for a dataset bundle. A bundle is one `.zip` file.

```bash
python main.py import cuny_20261127-141502.zip
python main.py show cuny
```

The [dashboard](https://huggingface.co/spaces/milwright/reddit-dashboard) opens the same `.zip` in a browser with nothing to install.

Today the create-app page at reddit.com/prefs/apps either stops at a policy notice or produces a client ID and secret that Reddit will not serve data to. The toolkit reports the second case as "Reddit accepted the client ID and secret, then refused to serve data."

## Route 3. You are a researcher at a university

Reddit's help center states that Reddit for Researchers is "the only official and authorized avenue for performing research using Reddit data." The program's page lists these conditions.

- Applicants and their principal investigators hold an affiliation with an accredited university and apply from an institutional email address.
- Each application names a sponsor, such as a faculty advisor, a department chair, or an official from the university's research office.
- The research is non-commercial.
- Reddit grants access for no more than one year and can revoke it after long inactivity or a breach of the program's requirements.
- Researchers do not mislead Reddit users about their identity or their research, and they coordinate with moderators before engaging a community.

To apply, open the [Reddit for Researchers Program](https://support.reddithelp.com/hc/en-us/articles/49381918834964-Reddit-for-Researchers-Program) page, follow its link to the request form, and select "I'm a researcher" as the reason for requesting access. The community at [r/reddit4researchers](https://www.reddit.com/r/reddit4researchers/) carries program news.

Reddit's help center also sets terms for research use. Read them in full before you design a study. In summary, the research must be academic and non-commercial, researchers may not redistribute Reddit data or products derived from it (trained models included), and published results must exclude Reddit data, credit Reddit, anonymize people, and reach Reddit with reasonable notice before publication.

Reddit decides how approved researchers receive data, and the route may differ from the public API this toolkit calls. Plan for both cases. If the program issues API credentials, `python main.py setup` accepts them. If it delivers files, `python main.py import posts.csv comments.csv` wraps CSV files as a dataset folder, and [DATASET_FORMAT.md](DATASET_FORMAT.md) lists the expected columns.

## If you teach with this toolkit

- Students cannot obtain their own credentials, so plan each assignment around datasets you provide or around the synthetic sample.
- `python main.py export <dataset>` produces a single `.zip` that students open with `python main.py import` or upload to the dashboard.
- Reddit's terms restrict redistribution of its data. Confirm with your IRB or research office that sharing a dataset inside a course fits those terms and your protocol, and never post a dataset publicly.
- The synthetic sample carries no such restriction. A program invents every row, and the generator is deterministic, so an entire class works from identical data.

## Routes that do not work

- **A new app at reddit.com/prefs/apps.** Reddit serves data to approved apps only, and it accepts no new requests for approval.
- **Reading reddit.com pages or `.json` addresses without credentials.** Reddit blocks traffic that does not sign in, and its terms prohibit collecting data that way.
- **Another person's credentials.** The account holder is responsible for their use, and sharing them breaks Reddit's terms.

## Error messages and their meaning

| The toolkit says | Likely cause |
|---|---|
| Reddit credentials are not set up | No `.env` file, empty values, or the placeholder text from `.env.example`. Run `python main.py setup`. |
| Reddit did not accept these credentials | HTTP 401. A typing error, a swapped ID and secret, or an app Reddit has removed. |
| Reddit accepted the client ID and secret, then refused to serve data | HTTP 403 on every community. The app exists and Reddit has not approved it, or Reddit has withdrawn its access. |
| Reddit refused access to r/name | HTTP 403 on one community. It is private or quarantined, and other communities still load. |
| Reddit asked the toolkit to slow down | HTTP 429. Too many requests. Wait a few minutes. The rows collected so far are saved. |
| The toolkit could not reach Reddit | No connection, or a campus network, VPN, or proxy that blocks Reddit. |

`python main.py check` runs these tests in order and prints the fix for the first one that fails.

## Sources

- Reddit Help, [Reddit for Researchers Program](https://support.reddithelp.com/hc/en-us/articles/49381918834964-Reddit-for-Researchers-Program)
- Reddit Help, [Developer Platform & Accessing Reddit Data](https://support.reddithelp.com/hc/en-us/articles/14945211791892-Developer-Platform-Accessing-Reddit-Data)
- Reddit's Responsible Builder Policy and Data API Terms, linked from the help pages above
- Reddit's announcements on [r/redditdev](https://www.reddit.com/r/redditdev/) (November 11, 2025 and September 30, 2026)
- TechRepublic, [Reddit Is Killing RSS and Public API Access: What Changes and When](https://www.techrepublic.com/article/news-reddit-rss-public-api-shutdown/) (October 2, 2026)
