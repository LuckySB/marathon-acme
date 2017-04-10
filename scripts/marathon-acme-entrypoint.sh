#!/usr/bin/env sh

# Options can be set using environment variables:
# MARATHON_ACME_ACME:      --acme
# MARATHON_ACME_EMAIL:     --email
# MARATHON_ACME_MARATHON:  --marathon
# MARATHON_ACME_LB:        --lb
# MARATHON_ACME_GROUP:     --group
# MARATHON_ACME_LOG_LEVEL: --log-level

# Listen on marathon PORT0:
# --listen:    0.0.0.0:$PORT0
# storage-dir: /var/lib/marathon-acme

exec marathon-acme \
  ${MARATHON_ACME_ACME:+--acme "$MARATHON_ACME_ACME"} \
  ${MARATHON_ACME_EMAIL:+--email "$MARATHON_ACME_EMAIL"} \
  ${MARATHON_ACME_MARATHON:+--marathon "$MARATHON_ACME_MARATHON"} \
  ${MARATHON_ACME_LB:+--lb "$MARATHON_ACME_LB"} \
  ${MARATHON_ACME_GROUP:+--group "$MARATHON_ACME_GROUP"} \
  ${MARATHON_ACME_LOG_LEVEL:+--log-level "$MARATHON_ACME_LOG_LEVEL"} \
  --listen 0.0.0.0:$PORT0 \
  /var/lib/marathon-acme \
  "$@"
