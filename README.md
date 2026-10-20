# vss-data – RegVil

Automation around the Altinn 3 apps used to follow up the digitaliseringstiltak in the
government's digitalisation strategy «Fremtidens digitale Norge – 2025 til 2030».

Every tiltak (1–123, some split in deltiltak such as 11a, 11b, …) goes through four
Altinn skjema, each its own Altinn app owned by `digdir`:

| Step | App | Next step |
|---|---|---|
| 1 | `regvil-2025-initiell` – registration of the tiltak | oppstart |
| 2 | `regvil-2025-oppstart` – start of the tiltak | status, or a new oppstart while the tiltak has not started (`Initiell.ErTiltaketPaabegynt = false`) |
| 3 | `regvil-2025-status` – status, every April and October | a new status while work goes on (`Status.ErArbeidAvsluttet = false`), slutt when finished |
| 4 | `regvil-2025-slutt` – final report | – |

A tiltak is identified through the whole process by its **report id**
(`digitaliseringstiltak_report_id`, e.g. `JAG`), stored as a tag on the form data of every
instance. The tiltak number itself is `Prefill.Tiltak.Nummer`. Report ids starting with
`ZZZ` (under tiltak 41) are test forms and are ignored by the manual scripts.

## Contents

- [Setup](#setup)
- [The event flow (app.py)](#the-event-flow-apppy)
- [Manual scripts – checking](#manual-scripts--checking)
- [Manual scripts – fixing](#manual-scripts--fixing)
- [Manual scripts – notifications and reminders](#manual-scripts--notifications-and-reminders)
- [Older scripts](#older-scripts)
- [Where things are logged](#where-things-are-logged)
- [Troubleshooting](#troubleshooting)

## Setup

```bash
pip install -r requirements.txt
```

`.env` in the repository root:

| Variable | Used for |
|---|---|
| `ENV` | `prod` or `test` – picks `config_files/<ENV>/` and the `<ENV>/` folders in blob storage |
| `MASKINPORTEN_SECRET_NAME` | Name of the secret with the Maskinporten private key (JWK) in Key Vault `keyvaultvss` – must be the key of the client in `config_files/<ENV>/maskinporten_config_*.json` |
| `MASKINPORTEN_SECRET_VAULT_URL` | Key Vault used by the older scripts at import |
| `BLOB_STORAGE_ACCOUNT_URL`, `BLOB_CONTAINER_NAME` | Blob storage with the event log and notification log |
| `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_CLIENT_SECRET` | Service principal for Key Vault and blob storage when running locally |

`config_files/<ENV>/`:

| File | Content |
|---|---|
| `config_client_file.json` | Altinn URLs (apps, Storage, Notifications) |
| `maskinporten_config_instance.json` | Maskinporten client, key id (`kid`) and scopes for instances |
| `maskinporten_config_varsling.json` | Same, for notifications and events |
| `maskinporten_endpoints.json` | Maskinporten URL per environment |
| `app_config.json` | Per app: tags, dates, email subject and body |
| `workflow_DAG.json` | Which app follows which |

All Altinn calls are Altinn 3 (`*.apps.altinn.no`, `platform.altinn.no`), authenticated with a
Maskinporten token exchanged for an Altinn token.

## The event flow (app.py)

`app.py` is a Flask server (Dockerfile, port 80) that Altinn Events calls when a skjema is
completed. It is the normal, automatic flow:

| Endpoint | What it does |
|---|---|
| `POST /httppost` | On `app.instance.process.completed`: downloads the completed skjema (`get_initiell_skjema.py`), creates the next skjema with the answers prefilled (`upload_single_skjema.py`) and notifies the contact person (`send_warning.py`). If it answers with an error, Altinn Events retries the event for a while. |
| `POST /send_reminder` | Runs `send_reminders.py` (header `X-Api-Key`) |
| `POST /send_seasonal_reminder` | Runs `send_seasonal_reminders.py` with subject and body from the headers |
| `GET /health` | Health check |

Modules used by the flow:

| File | What it does |
|---|---|
| `get_initiell_skjema.py` | Downloads a completed instance, logs it as `<Skjema>Downloaded` and decides the next app and its `visibleAfter` date |
| `upload_single_skjema.py` | Creates an instance in the next app, logs it as `<Skjema>Levert` and tags it with the report id |
| `send_warning.py` | Sends the email notification to `Prefill.Kontaktperson` and logs it as `Varsling1Send` |
| `clients/` | Altinn instance client, notification client and blob logging |
| `config/` | Config loading, date rules (`next_deadline`, `get_*_date`) and helpers |

## Manual scripts – checking

These only read from Altinn and blob storage. They take `ENV` from `.env` and write their
results to `storage_export/<ENV>/`. That folder contains personal data (names, emails):
keep it out of git.

### get_data_from_storage.py – export and reconciliation

Reads every instance of every app straight from Altinn Storage (all pages), parses the form
data and checks it against the event log.

```bash
python get_data_from_storage.py                           # all apps, completed instances
python get_data_from_storage.py --app regvil-2025-status  # one app
python get_data_from_storage.py --include-open            # also instances not submitted yet
```

| Output | Content |
|---|---|
| `<app>.json`, `<app>.csv` | One row per instance in the column layout of the app's table (for the database) |
| `reconciliation.csv` | Per completed instance: `missing_downloaded_blob` (the completed event was missed), `changed_by_user`, and fields that differ between Storage and the event log |
| `chain.csv` | Per downloaded skjema: was the next skjema created? `status` is `ok`, `missing_next_instance`, `download_without_report_id` or `end_of_workflow` |
| `problems_by_date.csv` | Problems counted per day and app, so an outage shows up as a cluster |

### get_open_instances.py – open (not submitted) instances

```bash
python get_open_instances.py
python get_open_instances.py --app regvil-2025-status
```

Writes `open_instances.csv`: one row per open instance with tiltak, visibility, whether the
recipient has opened or started it, the notifications sent and their delivery, and `flags`:

| Flag | Meaning |
|---|---|
| `no_data_element` | Empty instance (failed instantiation). `possible_source` lists the completed skjema that most likely created it (`last attempt` = certain) |
| `no_report_tag` | Form data without report id tag |
| `no_levert_blob` | Not created through the event flow, or its logging failed |
| `no_notification` | No notification logged since it was created |
| `notification_not_delivered` | Last notification has no receipt or was not delivered (run `notification_status.py` first) |
| `duplicate_open` | Another open instance in the same app has the same report id |
| `superseded` | A newer instance exists for the same report id (`superseded_by`) |
| `soft_deleted`, `overdue` | Soft deleted / `dueBefore` has passed |

### tiltak_overview.py – every tiltak through the process

```bash
python tiltak_overview.py
```

| Output | Content |
|---|---|
| `tiltak_timeline.csv` | One row per instance, per tiltak in time order: step, status round (`2026-04`, `2026-10`), instance id, created, visibleAfter, completed, state and a short summary of the answer |
| `tiltak_overview.csv` | One row per tiltak: initiell, oppstart, status rounds, slutt, current step, last answer, what it waits for, next expected step, and `issues`: `missing_next:<step>`, `missing_status_round:<round>`, `several_open`, `empty_instance`, `no_instances` |

## Manual scripts – fixing

All of these only show what they would do, unless `--send` / `--delete` is given.

### resend_missing_instances.py – create next skjema the flow failed to create

Uses the `missing_next_instance` rows in `chain.csv` (run `get_data_from_storage.py` first)
and the data in the `<Skjema>Downloaded` blob, i.e. exactly what the flow downloaded.
Creates the next instance with `upload_single_skjema.py` and notifies with `send_warning.py`.

```bash
python resend_missing_instances.py                     # show next app, date and report id per instance
python resend_missing_instances.py --diagnose          # compare the payloads with ones that worked
python resend_missing_instances.py --send --instance regvil-2025-status:<instance guid>   # one first
python resend_missing_instances.py --send              # all
```

`--diagnose` also writes the payloads to `resend_payloads/`.

### delete_empty_instances.py – remove empty instances

Hard deletes instances listed in a `;`-separated CSV with `app_name;instancePartyId;instanceId`
(a filtered copy of `open_instances.csv` works). Every instance is fetched first and only
deleted if it belongs to that app, is not completed and has **no** form data.

```bash
python delete_empty_instances.py empty_instances.csv            # check
python delete_empty_instances.py empty_instances.csv --delete   # delete
```

The result is written to `deleted_instances_<timestamp>.csv`. Hard deleted instances cannot
be restored.

## Manual scripts – notifications and reminders

All of them log what they send as `Varsling1Send`, like the event flow, so
`notification_status.py` collects the delivery receipts and the other scripts see the
tiltak as notified.

### send_missing_notifications.py – first notification that was never sent

Sends the notification for open instances flagged `no_notification` in `open_instances.csv`
(run `get_open_instances.py` first), or for a CSV with `app_name;instancePartyId;instanceId`.

```bash
python send_missing_notifications.py           # show
python send_missing_notifications.py --send    # send
```

The send time follows the instance's own `visibleAfter`: instances already visible are
notified now, the others are scheduled in Altinn for exactly when they become visible.
Instances that are completed, deleted, superseded, duplicated, empty or already notified
are skipped. The result is written to `sent_notifications_<timestamp>.csv`.

### send_status_reminders.py – reminders for overdue skjema

Reminds the contact person of every open skjema that should have been delivered: visible
before today, not completed or deleted, not superseded by a newer instance for the same
tiltak, not a test, and not notified the last day. By default all apps are checked, so each
tiltak is reminded about the skjema it is at now (initiell, oppstart, status or slutt).
Every email address gets **one** email listing all its tiltak.

```bash
# dry run: writes every email to reminders_preview_<timestamp>.txt
python send_status_reminders.py --subject "Påminnelse: ..." --body-file reminder.txt

# test: send to yourself, nothing is logged
python send_status_reminders.py --subject "Påminnelse: ..." --body-file reminder.txt --test-to me@digdir.no --limit 1 --send

# only some tiltak (11 also matches 11a, 11b, ...)
python send_status_reminders.py --subject "Påminnelse: ..." --body-file reminder.txt --tiltak 10 17 11b --send

# everybody
python send_status_reminders.py --subject "Påminnelse: ..." --body-file reminder.txt --send
```

| Option | Meaning |
|---|---|
| `--body-file` | UTF-8 text file with the email. `{tiltak}` is replaced by the list of tiltak, e.g. `- Tiltak 17: <name> (statusrapportering)`; without it the list is added at the end |
| `--subject` | Email subject (default: the app's `emailSubject`, or status's) |
| `--tiltak` | Only these tiltak numbers |
| `--app` | Only one app, e.g. `regvil-2025-status` (default: all) |
| `--recipient initiell` | Email the contact person given in the initiell skjema instead of `Prefill.Kontaktperson` |
| `--skip-notified-days N` | Skip tiltak notified the last N days (default 1; `0` to remind anyway) |
| `--test-to EMAIL` | Send everything to this address, subject marked `[TEST]`, nothing logged |
| `--limit N` | Send at most N emails |
| `--send` | Actually send |

The list of tiltak per email is written to `reminders_planned_*.csv` / `reminders_sent_*.csv`.

## Older scripts

| File | What it does | Notes |
|---|---|---|
| `upload_skjema.py` | Creates the initiell instances for all tiltak from `<ENV>/virksomheter_prefill_with_uuid.json` in blob storage | Run once at the start of the process |
| `send_initiell_warning.py` | Notifies the contact persons of the initiell instances | Run after `upload_skjema.py` |
| `notification_status.py` | Fetches the delivery status of every `Varsling1Send` and logs it as `Varsling1Recieved` | Run before checking deliveries in `get_open_instances.py` |
| `send_reminders.py` | Reminds open instances in all apps that are older than 14 days and not notified the last 14 days (`/send_reminder`) | Reads only the first page of instances from Storage |
| `send_seasonal_reminders.py` | Reminds all open status instances with subject/body from the request (`/send_seasonal_reminder`) | Also reminds instances that are not visible yet; replaced by `send_status_reminders.py` |
| `send_seasonal_reminders_manual.py` | Manual version of the above with a fixed text | Sending is commented out; replaced by `send_status_reminders.py` |
| `reinstansiering.py` | Recreates one instance in the **same** app, made visible now, then **deletes the original** and cancels a notification | Not for creating a missing next skjema – use `resend_missing_instances.py` |
| `delete_instance.py` | Deletes one instance (asks for app, party id and instance id) | Fails on instances without form data – use `delete_empty_instances.py` |
| `_delete_all_instances.py` | Deletes **all** instances of an app (asks to type `DELETE`) | Only for test |

## Where things are logged

Blob storage, container `BLOB_CONTAINER_NAME`:

| Path | Written by | Content |
|---|---|---|
| `<ENV>/event_log/<app>_<Skjema>Levert_<instance>.json` | `upload_*skjema.py` | Instance created: metadata, prefill data, report id |
| `<ENV>/event_log/<app>_<Skjema>Downloaded_<instance>.json` | `get_initiell_skjema.py` | Completed instance downloaded: metadata and answers. Overwritten if the event is processed again |
| `<ENV>/varsling/<report id>_<app>_Varsling1Send_<shipment>.json` | `send_warning.py` and the notification scripts | Notification sent: recipient, send time |
| `<ENV>/varsling/<report id>_<app>_Varsling1Recieved_<shipment>.json` | `notification_status.py` | Delivery status |

## Troubleshooting

- **`Unknown key identifier (kid) for client`** from Maskinporten: the key in
  `maskinporten_config_*.json` is expired or not registered on the client. Make a new key in
  Samarbeidsportalen for that environment, store the private JWK in Key Vault under
  `MASKINPORTEN_SECRET_NAME` and update `kid` in both config files. Keys expire – note the date.
  The Altinn Studio apps have their own Maskinporten key, which expires too.
- **`Instantiation of data elements failed`** (500) when creating an instance: the instance is
  created, but the app fails when storing the form data. Seen when the Altinn app's own
  Maskinporten key had expired. It leaves an empty instance behind: find it with
  `get_open_instances.py` (`no_data_element`), delete it with `delete_empty_instances.py` and
  create it again with `resend_missing_instances.py`.
- **A skjema was completed but nothing happened**: run `get_data_from_storage.py` and look in
  `reconciliation.csv` (`missing_downloaded_blob`) and `chain.csv` (`missing_next_instance`).
  `problems_by_date.csv` shows if it was a period of downtime.
- **The scripts use the wrong environment**: `ENV` in `.env` must match the secret in
  `MASKINPORTEN_SECRET_NAME`; prod config with a test key (or the other way round) fails.
