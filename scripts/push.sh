#!/usr/bin/env bash
# Push to main, retrying when GitHub has a temporary problem (HTTP 500s happen now and then).
for i in 1 2 3 4 5; do
  git pull -q --rebase origin main && git push -q origin HEAD:main && exit 0
  echo "push attempt $i failed; retrying in $((i * 20))s"
  sleep $((i * 20))
done
exit 1
