# Playthrough

A first day with hirejutsu on Windows, from install to the morning routine. The output comes from
a real run with the sample resume in `tests/fixtures/resume_sample.txt`. Paths are shortened to
`C:\Users\you` and the jobs are made up, so your picks will look different.

## 1. Install

Install Python 3.10 or newer from https://www.python.org/downloads/ (tick "Add python.exe to PATH")
and Git from https://git-scm.com/download/win. Then, in Command Prompt:

```
git clone https://github.com/Jay-Parmar/hirejutsu.git
cd hirejutsu
setup.bat
```

`setup.bat` takes a minute or two and ends with:

```
Created C:\Users\you\.hirejutsu\config.yaml
Next: put your resume in C:\Users\you\.hirejutsu and edit the config.

Done. Next:
  1. Copy your resume into the data folder shown above.
  2. .venv\Scripts\hirejutsu config --edit
  3. .venv\Scripts\hirejutsu run
  4. .venv\Scripts\hirejutsu schedule install
```

`C:\Users\you\.hirejutsu` is the data folder. Your resume, the config, the jobs and your history
all stay there.

Each time you open a new Command Prompt, go to the `hirejutsu` folder and run
`.venv\Scripts\activate` first. The rest of this page assumes you did.

## 2. Add your resume and say what you want

Copy your resume (PDF, DOCX, TXT or MD) into the data folder, then open the config:

```
hirejutsu config --edit
```

It opens `config.yaml` in Notepad. These settings are already in the file. Change them, then save
and close:

```yaml
resume: resume.txt

profile:
  locations: [remote, Bengaluru]

ranking:
  remote_from: [India, APAC, Asia]
```

- `resume`: your resume's file name. Leave it as `resume.pdf` if that is what you copied.
- `locations`: where you can work. `remote` lets remote jobs in.
- `remote_from`: places that include you. Remote jobs open only to other places, like
  "Remote (USA)", are skipped.

## 3. Check what it read

```
> hirejutsu resume
Resume: C:\Users\you\.hirejutsu\resume.txt (1010 characters)
Skills (27): Backend Development, Python, Go, AWS, Amazon EKS, Amazon RDS, Amazon SQS, MySQL, PostgreSQL, REST, Django, Celery, Redis, CI/CD, Jenkins, Docker, Unit Testing, pytest, React, Node.js, JavaScript, WordPress, SQL, Git, Kubernetes, Linux, Jira
Titles: Senior Software Engineer, Software Engineer
Years of experience: 9.6
Locations: remote, Bengaluru
```

9.6 years is too many for this resume, because its internship and freelance dates count too.
Settings under `profile` override what was read, so put the real number in the config:

```yaml
profile:
  years: 6
```

`profile.titles` replaces the titles it found, and `profile.skills` adds to the skills it found.

## 4. Check the setup

```
> hirejutsu doctor
ok    python      Python 3.13
ok    config      C:\Users\you\.hirejutsu\config.yaml
ok    resume      27 skills, Senior Software Engineer, Software Engineer, 6 years
warn  applicant   no details for forms and emails, run 'hirejutsu applicant --edit'
ok    sources     19 on: ashby, bamboohr, breezy, fourdayweek, greenhouse, hackernews, himalayas, jobicy, lever, personio, recruitee, remoteok, remotive, smartrecruiters, teamtailor, weworkremotely, workable, workday, workingnomads
warn  last fetch  never, run 'hirejutsu run'
warn  schedule    not scheduled, run 'hirejutsu schedule install'
ok    notify      off
ok    ai          off
ok    outreach    drafts from the template, no search
```

Fix any `fail` line. The warnings go away after the first run, step 8 and step 10.

## 5. First run

```
hirejutsu run --open
```

The first run takes 2 to 3 minutes. It downloads jobs from every source, picks the 10 best and
opens the day's report in your browser:

```
+-----------------+-------+------+---------+-----------------------+
| Source          | Found | New  | Seconds | Error                 |
+-----------------+-------+------+---------+-----------------------+
| ashby           | 1426  | 1426 | 8.0     |                       |
| greenhouse      | 4181  | 4181 | 56.6    |                       |
| jobicy          | 1000  | 1000 | 4.1     |                       |
| lever           | 1027  | 1027 | 25.6    |                       |
| smartrecruiters | 5201  | 5201 | 53.5    |                       |
| workday         | 4340  | 4340 | 140.3   | 1 of 30 boards failed |
| ...             |       |      |         |                       |
+-----------------+-------+------+---------+-----------------------+
Picks for 2026-10-21
+---+-------+-------+-------------------------+---------+------------------+--------+------------+
| # | ID    | Score | Job                     | Company | Location         | Salary | Posted     |
+---+-------+-------+-------------------------+---------+------------------+--------+------------+
| 1 | 1784  | 0.69  | Senior Backend Engineer | Hooli   | Bangalore        |        | today      |
| 2 | 18227 | 0.69  | Senior DevOps Engineer  | Globex  | APAC             |        | yesterday  |
| 3 | 7802  | 0.68  | Staff Software Engineer | Initech | Remote           |        | 3 days ago |
| 4 | 1789  | 0.67  | Platform Engineer       | Hooli   | Bangalore, India |        | today      |
| 5 | 6757  | 0.65  | Software Engineer, Auth | Contoso | Anywhere         |        | 4 days ago |
+---+-------+-------+-------------------------+---------+------------------+--------+------------+
1. https://... via Greenhouse career pages
2. https://... via Working Nomads
3. https://... via Lever career pages
Saved C:\Users\you\.hirejutsu\reports\2026-10-21.md
Saved C:\Users\you\.hirejutsu\reports\2026-10-21.html
```

About 18,000 jobs came in on this run. One Workday board answered "too many requests", so it was
skipped and the others still ran. It is tried again on the next run.

## 6. Read the picks

The report shows why each job was picked and links to the job, so you can apply there:

```
## 1. Senior Backend Engineer at Hooli
Bangalore | posted today | via Greenhouse career pages | score 0.69 | id 1784

- Skills: MySQL, Docker, REST (12 of 27)
- Asks 8+ years, you have 6
- In Bengaluru
- Posted today
- Apply: https://...
```

To see how one job scored:

```
> hirejutsu explain 678
Senior Software Engineer at Northwind (id 678)
Score 0.63
+-----------+-------+--------+
| Part      | Score | Weight |
+-----------+-------+--------+
| skills    | 0.72  | 0.35   |
| text      | 0.10  | 0.20   |
| title     | 1.00  | 0.20   |
| seniority | 1.00  | 0.10   |
| freshness | 0.12  | 0.10   |
| location  | 1.00  | 0.05   |
+-----------+-------+--------+
Filters
  max_age_days: passed
  location: passed
  relevance: passed
  shortlist: passed
Reasons
  - Skills: Jenkins, REST, Kubernetes (7 of 27)
  - Title close to Software Engineer
  - In Bengaluru
  - Posted 9 days ago
```

The Ranking section of the README explains each part.

## 7. Apply and record it

Apply on the job's page, then tell hirejutsu. `review` goes through the picks one at a time:

```
> hirejutsu review

Pick 1 of 10: Senior Backend Engineer
Hooli | Bangalore | score 0.69
- Skills: MySQL, Docker, REST (12 of 27)
- Asks 8+ years, you have 6
- In Bengaluru
- Posted today
https://...
[a]pplied [s]kip [l]ater [o]pen [n]ext [q]uit a
Marked as applied.
```

`o` opens the job in your browser, `l` keeps it for later, `n` leaves it as it is and `q` stops.
Or mark several at once, by today's pick numbers with `-t` or by the IDs:

```
hirejutsu applied -t 1 3
hirejutsu skip -t 2
hirejutsu save -t 4
```

When you hear back:

```
> hirejutsu status 678 interview --note "call on Tuesday"
Marked job 678 as interview: Senior Software Engineer at Northwind
> hirejutsu note 678 recruiter called back
Added a note to job 678: Senior Software Engineer at Northwind
```

A job is only ever picked once, so tomorrow's 10 are ones you have not seen yet.

## 8. Write to recruiters

Job sites often give no answer, so write to someone at the company as well. The emails are signed
with your applicant details, so start those once:

```
hirejutsu applicant --edit
```

It creates `applicant.yaml` with the name, email, phone and links found in your resume. Then:

```
> hirejutsu outreach --open
Left out 3 of 10 picks because they come from job boards. Add their sources to outreach.sources to write about them too.
                       Recruiter emails for 2026-11-04
+-------+-------------------------+---------+-------------------+----------+
| ID    | Job                     | Company | Write to          | How sure |
+-------+-------------------------+---------+-------------------+----------+
| 1784  | Senior Backend Engineer | Hooli   | careers@hooli.com | site     |
| 7802  | Staff Software Engineer | Initech | nobody found      |          |
| ...   |                         |         |                   |          |
+-------+-------------------------+---------+-------------------+----------+
```

The page that opens has a draft for each job:

```
Subject: Senior Backend Engineer role at Hooli

Hi Hooli team,

I saw the Senior Backend Engineer role at Hooli (https://...) and wanted to write to you directly.
I have 6 years of experience, much of it with MySQL, Docker and REST, which the role asks for.
Could you pass my profile to the hiring manager, or would you have time for a short call?
Thank you for your time.

Best regards,
Priya Sharma
+91 9876543210
```

Click an address to open the draft in your mail app, attach your resume and send it. Then note it,
so the job is not drafted again:

```
hirejutsu outreach sent 1784 careers@hooli.com
```

Without a search key, an address only shows up when the job post or the company's site lists one,
which big companies rarely do, so many jobs say "nobody found" and give two links to look someone
up yourself. With a free Tavily key (see Recruiter emails in the README) it also finds recruiters by
name and suggests their likely addresses, marked as guesses since they can bounce.

## 9. Fill Workday forms

Many big companies take applications on Workday, with job links on myworkdayjobs.com, and the forms
are long. Install the extra once:

```
pip install -e ".[workday]"
```

Then for each job:

```
hirejutsu workday <job link>
```

An Edge window opens on the job. Click Apply and sign in. On each step hirejutsu fills what it knows
from `applicant.yaml`, prints what it filled and what it left for you, and waits. Check the step and
click Save and Continue yourself. At the Review step it stops: check the application and submit it.
If a field stays empty that you expected filled, run it again with `--dump`. The file it saves in
the `logs` folder shows what to fix.

## 10. Let it run every morning

```
hirejutsu schedule install
```

This adds a Windows task that runs hirejutsu every day at 09:00 (`--time 07:30` for another time).
If the PC is off or asleep at 09:00, it runs as soon as you log in. Each scheduled run writes a
log to the `logs` folder in the data folder, and `hirejutsu schedule status` shows the last and
next run.

From then on, each morning:

1. Open the newest report in `C:\Users\you\.hirejutsu\reports`, or run `hirejutsu today`.
2. Apply to the ones you like.
3. Record them with `hirejutsu review`.

Leave `run` to the schedule, and use `today` to see the list again. A second `run` on the same
day picks a fresh list, without the jobs you already marked, so the pick numbers change.

To get the picks by email, Telegram, Discord, Slack or ntfy, see Notifications in the README.

## 11. Look back

```
> hirejutsu stats
Jobs by status
+-----------+-------+
| Status    |  Jobs |
+-----------+-------+
| new       | 18247 |
| saved     |     1 |
| applied   |     1 |
| interview |     1 |
| offer     |     0 |
| rejected  |     0 |
| skipped   |     1 |
+-----------+-------+
Applications per week
+------------+---------+----+
| Week of    | Applied |    |
+------------+---------+----+
| 2026-10-05 |       0 |    |
| 2026-10-12 |       0 |    |
| 2026-10-19 |       2 | ## |
+------------+---------+----+
Response rate: 50% (1 of 2 applications got an interview or offer)
Picks shown: 10
Top companies: Northwind (1), Globex (1)
```

```
hirejutsu list --status applied   # what you applied to
hirejutsu show 678                # one job with its notes and history
hirejutsu export                  # every tracked job to a CSV in the data folder
```

## 12. Make the picks better

- Too senior or too junior: set `profile.years`.
- Wrong kind of job: add words to `ranking.exclude_title_words`, like `[sales, intern]`.
- Missing a company: `hirejutsu companies add <careers page or job link>`.
- After changing the config, `hirejutsu top -n 30` shows the new ranking without changing
  today's picks.
- Naukri, LinkedIn and Indeed are optional and off by default. See the README before turning
  them on.

## 13. Update and fix things

- Update: `git pull`, then `setup.bat`. If you move the folder or delete `.venv`, run
  `hirejutsu schedule install` again.
- Something wrong: run `hirejutsu doctor` first. Add `-v` to any command for debug logs.
- A source that fails is skipped and tried again on the next run. `hirejutsu sources` shows each
  source's last fetch.
