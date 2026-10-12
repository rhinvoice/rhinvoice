# Backups

Rhinvoice keeps everything in its PostgreSQL database: customers, articles, documents, the
archived PDFs of issued documents, the logo and the settings. The `backup` container saves
the database with [restic](https://restic.net): **encrypted, deduplicated and compressed**,
to a target of your choice.

- **When:** daily (02:00 by default) and about two minutes after documents were issued or
  cancelled (several in a row give one backup). *Settings → Backup → Back up now* asks for
  one at once.
- **Kept:** 7 daily, 4 weekly, 12 monthly and **every yearly** backup. Invoices must be kept
  for 10 years (OR 958f, GoBD, BAO); yearly backups are never deleted. Old backups are
  removed on Sundays, when a sample of 5 % of the data is also verified.
- **Not backed up:** an installation without company data (a fresh one). Its empty database
  must never become the latest backup.
- **Shown:** the dashboard warns when the last successful backup is older than 24 hours
  or backups are not set up.

## Setting it up

Choose a target and write it to `.env` (next to `compose.yml`), then restart:
`docker compose up -d`.

```dotenv
RESTIC_PASSWORD='a-long-random-password'   # encrypts the backups
RESTIC_REPOSITORY=...                      # see below
```

> **Keep the password somewhere else too** (password manager, printed in a safe).
> Without it, nobody can restore the backups – not even you.

Create the password with `openssl rand -hex 32`, or put it in single quotes: Docker Compose
would otherwise change a `$` in it, and the password in your password manager would no
longer be the one that encrypts the backups.

### S3-compatible storage (Backblaze B2, Infomaniak Swiss Backup, AWS, Wasabi …)

```dotenv
RESTIC_REPOSITORY=s3:https://s3.eu-central-003.backblazeb2.com/my-bucket/rhinvoice
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
```

Use a key that may only access this bucket.

### SFTP (NAS, server)

```dotenv
RESTIC_REPOSITORY=sftp:backup@nas.example:/backups/rhinvoice
```

The container needs the SSH key and the server's host key (`known_hosts`: nobody can confirm
an unknown server). Mount them, e.g. in a `compose.override.yml`:

```yaml
services:
  backup:
    volumes:
      - ./ssh:/home/backup/.ssh:ro   # id_ed25519 and known_hosts
```

```bash
ssh-keyscan nas.example > ssh/known_hosts
sudo chown -R 10001 ssh && chmod 700 ssh && chmod 600 ssh/id_ed25519   # the container's user
```

### Dropbox, Google Drive and other cloud storage (rclone)

restic reaches them through [rclone](https://rclone.org), which is part of the backup
container. The backups are encrypted before they leave the machine: the cloud provider only
stores unreadable blocks. The first backup holds every archived PDF; later ones add only
what changed, usually a few kilobytes.

1. **Allow access**, once, on a computer with a web browser (it does not need to be the
   server): install rclone 1.75 or newer ([rclone.org/downloads](https://rclone.org/downloads/),
   on a Mac `brew install rclone`) and run

   ```bash
   rclone authorize "dropbox"
   ```

   Log in to Dropbox in the browser that opens and allow access. The terminal then prints
   a token between `Paste the following into your remote machine --->` and `<---End paste`:
   one line starting with `{"access_token":`.

2. **Hand the token to the backup container**, on the server, in the Rhinvoice folder.
   `read` keeps the token out of the screen and the shell history:

   ```bash
   read -rs TOKEN    # paste the token, press Enter
   docker compose run --rm --no-deps backup rclone config create dropbox dropbox \
     config_refresh_token false token "$TOKEN"
   unset TOKEN
   ```

   The configuration is kept, unencrypted, in the volume `backup-rclone`; rclone renews the
   access there by itself. Whoever controls the server can read it, as they can read the
   database. rclone's own Dropbox app may access your whole Dropbox: for access to one folder
   only, create your own Dropbox app with "App folder" access
   ([rclone.org/dropbox](https://rclone.org/dropbox/#get-your-own-dropbox-app-id)) and add
   its `client_id` and `client_secret` to both commands.

3. **Choose the folder** in `.env` and restart (`docker compose up -d`):

   ```dotenv
   RESTIC_REPOSITORY=rclone:dropbox:Rhinvoice-Backup
   ```

4. **Try it:** `docker compose exec backup rhinvoice-backup backup`. The folder
   `Rhinvoice-Backup` appears in your Dropbox; *Settings → Backup* shows the backup.

**Google Drive** works the same. Ask only for access to the files rclone creates itself
(the scope must be chosen when authorizing; setting it later does not narrow the token):

```bash
rclone authorize "drive" --drive-scope drive.file
```

```bash
read -rs TOKEN
docker compose run --rm --no-deps backup rclone config create gdrive drive \
  scope drive.file config_refresh_token false token "$TOKEN"
unset TOKEN
```

and `RESTIC_REPOSITORY=rclone:gdrive:Rhinvoice-Backup`.

For other providers (OneDrive, kDrive and other WebDAV storage, …) run
`docker compose run --rm --no-deps backup rclone config`, answer "No" when asked whether to
use a web browser automatically and follow the rclone documentation of the provider.
Name the remote as you like and use it in `RESTIC_REPOSITORY=rclone:<name>:<folder>`.

### A folder of this machine (iCloud, Nextcloud, Dropbox app, USB disk)

```dotenv
RESTIC_REPOSITORY=/repository
BACKUP_LOCAL_DIR=/Users/me/Library/Mobile Documents/com~apple~CloudDocs/Rhinvoice-Backup
```

The container writes as user 10001; on Linux make the folder writable for it
(`sudo chown 10001 /path/to/folder`). Without `BACKUP_LOCAL_DIR` the backups land in a Docker
volume on the same disk – that protects against mistakes, not against a broken disk.

## Checking

```bash
docker compose logs backup                            # what the container does
docker compose exec backup rhinvoice-backup snapshots # list the backups
docker compose exec backup rhinvoice-backup check     # verify the repository
docker compose exec backup rhinvoice-backup backup    # back up now
docker compose exec backup rhinvoice-backup rclone lsd dropbox:  # an rclone target is reachable
```

## Restoring

Restoring **replaces the whole database** with the state of a backup. It runs in one
transaction: if anything fails, nothing changes.

```bash
docker compose exec backup rhinvoice-backup snapshots   # pick a snapshot ID
docker compose stop app backup
docker compose run --rm --no-deps backup restore latest # or the ID, e.g. 52365e00
docker compose start app backup
```

From the source folder: `make restore SNAPSHOT=latest`.

**On a new machine:** install Rhinvoice as in [install.md](install.md) with the same
`RESTIC_REPOSITORY` and `RESTIC_PASSWORD`. Start **only the database** first
(`docker compose up -d db`), then restore as above and start everything
(`docker compose up -d`). The app creates the database tables itself; the restore replaces them.

Try a restore once after setting up, e.g. with a second installation next to the first
(see [install.md](install.md), "Trying it next to an existing installation"). Give it the
same `RESTIC_REPOSITORY` and `RESTIC_PASSWORD` only for restoring, and **do not run its backup
container** with them (`docker compose stop backup`): two installations backing up to one
repository would mix their backups. If you really want that, give each its own `BACKUP_HOST`.

**Database versions:** the backup container includes the tools of PostgreSQL 17, like the
`db` container. When PostgreSQL gets a new major version, both are updated together.
