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

### Dropbox and other cloud storage (rclone)

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

4. **Try it:** wait until `docker compose logs backup` shows `waiting for requests`, then
   run `docker compose exec backup rhinvoice-backup backup`. The folder `Rhinvoice-Backup`
   appears in your Dropbox; *Settings → Backup* shows the backup. Creating the repository on
   the first start takes about a minute over rclone; a backup asked for before that fails
   with `config file already exists`, although nothing is wrong.

For other providers (OneDrive, kDrive and other WebDAV storage, …) run
`docker compose run --rm --no-deps backup rclone config`, answer "No" when asked whether to
use a web browser automatically and follow the rclone documentation of the provider.
Name the remote as you like and use it in `RESTIC_REPOSITORY=rclone:<name>:<folder>`.

### Google Drive (rclone, with your own OAuth client)

Google Drive needs a **client ID of your own**. rclone's shared one "is being retired and will
stop working during 2026" ([rclone.org/drive](https://rclone.org/drive/#making-your-own-client-id));
a remote that still uses it logs a `NOTICE` on every backup. Creating one is free and takes
about ten minutes in the Google Cloud console. The menus there change now and then: if a
name below is not where you look, follow the links, and compare with rclone's own steps.

1. **Create a project:** <https://console.cloud.google.com/projectcreate>, any name (e.g.
   "Rhinvoice Backup"). In all following steps the project must be the one selected at the top
   of the page.
2. **Enable the Google Drive API:**
   <https://console.cloud.google.com/apis/library/drive.googleapis.com>, *Enable*.
3. **Consent screen:** <https://console.cloud.google.com/auth/overview>, *Get started*: an app
   name (e.g. "rclone"), your address as support e-mail, audience **External**, your address as
   contact, *Create*.
4. **Scope:** <https://console.cloud.google.com/auth/scopes>, add
   `https://www.googleapis.com/auth/drive.file`, *Update*, *Save*. With this scope the client
   sees only the files it creates itself, not the rest of your Drive.
5. **Client:** <https://console.cloud.google.com/auth/clients>, *Create client*, type
   **Desktop app**. Keep the **client ID** and the **client secret** at once (password
   manager): the secret is shown only now.
6. **Publish the app:** <https://console.cloud.google.com/auth/audience>, *Publish app*. The
   status must read **In production**.

> **Do not skip step 6.** While the status is "Testing", Google ends the access after seven
> days: the backups would stop a week later without anything having changed. An app for your
> own use needs no verification by Google; when logging in you accept the warning that the
> app is not verified.

Then, as for Dropbox, on a computer with a web browser and rclone 1.75 or newer:

```bash
read -rs CID        # paste the client ID, press Enter
read -rs CSECRET    # paste the client secret, press Enter
rclone authorize "drive" "$CID" "$CSECRET" --drive-scope drive.file
```

The scope must be chosen when authorizing; setting it later does not narrow the token. Log in
and allow access; the terminal prints the token (one line starting with `{"access_token":`).
On the server, in the Rhinvoice folder (set `CID` and `CSECRET` there the same way if it is
another machine):

```bash
read -rs TOKEN
docker compose run --rm --no-deps backup rclone config create gdrive drive \
  client_id "$CID" client_secret "$CSECRET" scope drive.file \
  config_refresh_token false token "$TOKEN"
unset TOKEN CID CSECRET
```

Choose the folder in `.env`, restart (`docker compose up -d`) and try it as in step 4 above:

```dotenv
RESTIC_REPOSITORY=rclone:gdrive:Rhinvoice-Backup
```

**Folders you made yourself are invisible.** With `drive.file` rclone does not see a folder
you created in the browser. If `RESTIC_REPOSITORY` names such a folder (say `Backups/…`),
a second folder of the same name appears next to it. Let rclone create the folder.

#### Moving an existing Google Drive backup to your own client ID

The new client does not see what the old one wrote: the repository made with rclone's shared
client ID is invisible to it. The backup container therefore **creates a new, empty
repository** in a second folder of the same name, and it does not back up by itself right
then. Until you start a backup by hand there is no backup the installation can reach, while
the dashboard still shows the last successful one.

Do steps 1 to 6 above, authorize as shown, then on the server:

```bash
docker compose stop backup
read -rs CID; read -rs CSECRET; read -rs TOKEN
docker compose run --rm --no-deps backup rclone config delete gdrive
docker compose run --rm --no-deps backup rclone config create gdrive drive \
  client_id "$CID" client_secret "$CSECRET" scope drive.file \
  config_refresh_token false token "$TOKEN"
unset TOKEN CID CSECRET
docker compose up -d backup
docker compose logs -f backup                            # wait for "waiting for requests"
docker compose exec backup rhinvoice-backup backup       # needed: the new repository is empty
docker compose exec backup rhinvoice-backup snapshots
docker compose exec backup rhinvoice-backup check
```

The `NOTICE` about the shared client ID is gone from the log. The old folder with the earlier
backups stays in your Drive; it can only be opened with the old access. Delete it in the
browser once the new backup is checked, or keep it until you have tried a restore.

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
docker compose logs backup | grep NOTICE              # Google Drive: still on rclone's shared client ID?
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

### Trying a restore next to the running installation

Try a restore once after setting up. A second installation in its own folder restores the
latest backup without touching the first. The example assumes the installation is in
`~/rhinvoice` with the project name `rhinvoice`; use your own names.

```bash
mkdir ~/rhinvoice-restoretest && cd ~/rhinvoice-restoretest
cp ~/rhinvoice/compose.yml ~/rhinvoice/.env .
# Its own project name and port, and no recurring invoices from the copy.
# On Linux: sed -i 's/…/…/' .env (without the '').
sed -i '' 's/^COMPOSE_PROJECT_NAME=.*/COMPOSE_PROJECT_NAME=rhinvoice-restoretest/; s/^RHINVOICE_PORT=.*/RHINVOICE_PORT=8100/' .env
echo 'RHINVOICE_RECURRING=false' >> .env
grep -E '^(COMPOSE_PROJECT_NAME|RHINVOICE_PORT|RHINVOICE_RECURRING)=' .env   # check all three

docker compose up -d db
# Only with an rclone target (Dropbox, Google Drive …): the access is kept in a volume of
# each project. Create the copy's volumes, then copy the configuration into them.
docker compose run --rm --no-deps backup rclone version
docker run --rm -v rhinvoice_backup-rclone:/from:ro \
  -v rhinvoice-restoretest_backup-rclone:/to alpine sh -c 'cp -a /from/. /to/'

docker compose run --rm --no-deps backup snapshots
docker compose run --rm --no-deps backup restore latest
docker compose up -d app        # the app only, never the copy's backup container
```

Open <http://localhost:8100>, log in and look at a few invoices. Send nothing from the copy:
the mail server settings were restored with everything else. Then remove it:

```bash
grep '^COMPOSE_PROJECT_NAME=' .env     # must show rhinvoice-restoretest
docker compose down -v
cd ~ && rm -rf ~/rhinvoice-restoretest
```

- **The project name decides what a command touches.** Without a changed
  `COMPOSE_PROJECT_NAME` every command above, also `down -v`, acts on the real installation.
  If `.env` has no such line, add it instead of replacing it.
- **Start the app by name.** A plain `docker compose up -d` also starts the copy's backup
  container: two installations backing up to one repository would mix their backups. If you
  really want that, give each its own `BACKUP_HOST`.
- **Volume names follow the project name:** `<project>_backup-rclone`; `docker volume ls`
  lists them.
- `RHINVOICE_RECURRING=false` keeps the copy from writing and mailing the recurring invoices
  of the real installation.

**Database versions:** the backup container includes the tools of PostgreSQL 17, like the
`db` container. When PostgreSQL gets a new major version, both are updated together.
