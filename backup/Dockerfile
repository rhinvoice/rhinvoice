# Backup container: pg_dump into a restic repository (docs/backup.md).
FROM restic/restic:0.19.1@sha256:136600b6ff6843d61d355f7f71f460a166429f35de6fd11b568fece3c9a4d510 AS restic
# restic reaches Dropbox, Google Drive, OneDrive, WebDAV ... through rclone.
FROM rclone/rclone:1.75.2@sha256:2687085f718d3c628f7fdfb77c52a1d344332aed543110bb88088f2c70d43eb5 AS rclone

FROM alpine:3.22@sha256:5291449c3df73caf6ed85e649dec1b9e818b39a5d8c871e97afc13e9cd5e8fa8
# pg_dump must match the major version of the database (postgres:17).
RUN apk add --no-cache postgresql17-client jq tzdata ca-certificates openssh-client \
    && addgroup -S -g 10001 backup \
    && adduser -S -D -H -u 10001 -G backup -h /home/backup backup \
    && install -d -o backup -g backup /cache /home/backup /repository /rclone
COPY --from=restic /usr/bin/restic /usr/local/bin/restic
COPY --from=rclone /usr/local/bin/rclone /usr/local/bin/rclone
COPY backup/rhinvoice-backup.sh /usr/local/bin/rhinvoice-backup
# rclone saves renewed access tokens to its configuration: /rclone must be writable.
ENV RESTIC_CACHE_DIR=/cache \
    RCLONE_CONFIG=/rclone/rclone.conf \
    RCLONE_CACHE_DIR=/cache/rclone \
    HOME=/home/backup
USER backup
# The loop touches the heartbeat at least every few minutes; a backup may take a while.
HEALTHCHECK --interval=5m --timeout=10s --start-period=10m \
    CMD [ -n "$(find /tmp/heartbeat -mmin -90 2>/dev/null)" ]
ENTRYPOINT ["rhinvoice-backup"]
CMD ["run"]
