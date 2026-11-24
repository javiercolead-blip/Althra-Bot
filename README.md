# Althra Bot: an opportunity scout

Althra Bot scans Canadian giveaway sources twice a day and throws out anything you can't enter (US-only, another province only, wrong age). It ranks the rest by how worth it they are and puts them in a colour-coded spreadsheet for you to work through.

You still click **Submit** yourself. Most contest rules disqualify automated entries, and a disqualification usually means losing a prize you already won. The bot does the finding, filtering, ranking and reminding.

## Your daily routine (about 15 minutes)

1. Open the **Tracker** sheet. Rows needing action are at the top.
2. Work through the **🔁 Enter Again** and **⭐ To Enter** rows. Open the link, enter, and set the status to **✅ Entered**.
3. If you win, set the row to **🏆 Won**.
4. Found a contest somewhere else? Paste its link in a new row. The bot picks it up on the next run.

| Status | Colour | Meaning |
|---|---|---|
| 🔁 Enter Again | blue | Daily or weekly contest that's open for another entry |
| ⭐ To Enter | yellow | Today's queue: the best new finds (25 at most) |
| 🆕 New | white | Found, but not in today's top picks |
| ✅ Entered | light green | Done. Daily and weekly contests flip back to 🔁 on their own |
| 🏆 Won | bright green | Kept forever |
| ⌛ Expired | grey | Closed before you entered. Cleared after 2 weeks |
| 🚫 Skip | red | Not interested. The bot leaves it alone |
| ⛔ Not Eligible | red / grey | The rules exclude you |

The **Summary** tab counts how many rows have each status, plus your total entries.

## How it ranks

`score = prize size (log scale) + locality bonus + repeat-entry bonus + interest match + closing-soon bonus`

A BC-only contest gets +20 and a Canada-only one +12, because a smaller pool of entrants gives you better odds. Worldwide contests get −5. Daily-entry contests get +8 because every entry counts. You can change your profile and interests in `config/profile.yaml`.

## How it works

```
config/sources.yaml ─▶ scouts (RSS / HTML) ─▶ enrich (eligibility, value, end date, frequency, score)
                                                   │
Google Sheet / tracker.xlsx ◀─▶ tracker (merges your edits, sets statuses, builds today's queue)
                                                   │
                                     data/opportunities.json (memory, committed by the bot)
```

- `althra/scouts/`: one scout per source type. A broken source is logged and skipped, so it never stops the run.
- `althra/enrich.py`: eligibility rules for your profile, prize value detection, end-date parsing and scoring.
- `althra/tracker.py`: status logic: the daily queue, re-entry reminders, expiry and cleanup.
- `althra/sheets/`: the Excel and Google Sheets writers, both with a status dropdown and row colours.
- `.github/workflows/scout.yml`: runs at about 6am and 5pm Vancouver time. You can also run it from the **Actions** tab.

## Setup

### 1. Google Sheet (one time, about 10 minutes)

1. Go to https://console.cloud.google.com, create a project, and enable the **Google Sheets API**.
2. Go to **IAM & Admin → Service Accounts → Create**, then open the account and choose **Keys → Add key → JSON**. A key file downloads.
3. Create an empty Google Sheet. Click **Share** and add the service account's email (`…@….iam.gserviceaccount.com`) as an **Editor**.
4. In this GitHub repo, go to **Settings → Secrets and variables → Actions** and add two secrets:
   - `GOOGLE_SHEET_ID`: the long id in the sheet URL (`docs.google.com/spreadsheets/d/<THIS>/edit`)
   - `GOOGLE_SERVICE_ACCOUNT_JSON`: the full contents of the key file

Without these secrets the bot still runs, but it only updates `data/tracker.xlsx` in the repo.

### 2. Turn it on

Open the **Actions** tab, select **Scout**, and click **Run workflow**. The log has a line for each source:

```
[scout] Contest Canada: 34 items
[scout] Contest Queen: FAILED (404 …)
```

If a source fails, fix its URL in `config/sources.yaml` or set `enabled: false`. Any RSS feed works, and most contest blogs have one at `/feed/`.

### Run locally

```bash
pip install -r requirements.txt
python -m pytest            # tests
python -m althra run        # writes data/tracker.xlsx (+ Google Sheet if the env vars are set)
```

## Tips

- Use a separate email or a Gmail alias (`you+contests@gmail.com`) for entries.
- Canadian contests require a skill-testing question when you win. That's normal.
- A "winner" notice that asks you to pay a fee or hand over banking details is a scam.
- Prizes are generally not taxable in Canada.

## Roadmap

- [ ] Win detector: scan Gmail for "congratulations / you've won" and mark rows 🏆 automatically
- [ ] Claude reads the official rules page when the summary doesn't settle eligibility
- [ ] Remote sales job scout (Indeed, LinkedIn, Wellfound) with tailored application drafts
- [ ] Free local events in Vancouver (Luma, Meetup, Eventbrite, City of Vancouver)
