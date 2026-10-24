# Importing activities from FIT, TCX and GPX files

COACH can read workout files from any brand. Imported activities behave like Garmin ones: they complete the planned session of the same day and sport, count in the statistics, the estimated current level and the weekly volume, and are shown to the coach.

## How to import

*Profile > Preferences > Import FIT, TCX, GPX files*, choose up to 20 files (10 MB each). For each file the screen says **Imported**, **Duplicate** (already known) or **Unreadable** (with the reason). *View the plan* shows the matching.

- Format is detected from the **content**, not the extension.
- FIT is preferred (complete data). TCX is fine. GPX has no calories and often no heart rate; a GPX route without timestamps cannot be dated and is refused.
- A workout is a **duplicate** if the same file was imported before, or if an activity from Garmin or another import starts within 2 minutes with a similar duration (so the same session exported as FIT and TCX is counted once).
- Activities older than 2 years or dated in the future are refused.
- The totals are kept (sport, start, duration, distance, elevation gain, average and max heart rate, calories) with **simplified curves** of the session (heart rate, speed, elevation, cadence, power when the file has them; about 400 points) shown on the session page. The GPS track is **not** stored: no latitude or longitude is kept or shown, and nothing is sent to a third party. Missing values stay empty (never 0). Curves are deleted with the activity.
- Times in files are UTC; they are converted to the time zone of your browser.
- Disconnecting Garmin with "delete my activities" removes only Garmin activities, not imported ones.

## How to export from each brand

| Brand | Where to find the file |
|---|---|
| **Coros** | Coros app: open the activity, top-right menu (share / "…"), *Export data*, choose **FIT** (or TCX/GPX). The file is sent through the share sheet (save to Files, e-mail it to yourself). Coros also offers the export on the web Training Hub (activity page, *Export data*). |
| **Suunto** | Suunto app, or the web service: open the workout, *Share / Export*, **FIT** (the app exports a FIT or GPX file; choose FIT when offered). |
| **Polar** | Polar Flow (web, flow.polar.com): open the training session, the *export* button (top right of the session), choose **TCX** or **GPX**. Bulk data: *Account > Download your data*. |
| **Wahoo** | ELEMNT companion app: open the workout, share icon, *Export FIT*. Or the ELEMNT/SYSTM web history. The `.fit` file is also on the device over USB, in the workouts folder. |
| **Apple Watch / Apple Health** | Apple Health exports everything in one `export.xml` (not supported yet). To import single workouts use a free "workout exporter" app that writes **GPX or FIT** per workout (Apple's Workout app itself does not export files). |
| **Garmin (offline)** | Garmin Connect web: activity, gear icon, *Export Original* (a ZIP containing the `.fit`; unzip it first) or *Export to TCX / GPX*. Or plug the watch in USB: `GARMIN/Activity/*.fit`. |

Menus change between app versions; if a name differs, look for "Export" or "Share" on the activity page. Keep in mind that a ZIP must be unzipped first (a ZIP is not accepted yet).

## Limits and what is not done yet

Apple Health `export.xml` as a whole, ZIP files or folders, and automatic import (watching a folder, share target) are tracked in a follow-up issue. Strength sessions imported from a watch have no sets or repetitions: COACH never invents them.

## For developers

See [integrations.md](integrations.md#fit--tcx--gpx-file-import-built-in): parsers are pure functions in `app/activity_import/parse.py`; the upload route is in `app/activity_import/api.py`.
