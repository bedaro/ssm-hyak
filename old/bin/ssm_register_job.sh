#!/bin/sh
# Registers a job so ssm_sync_jobs can sync it

STATEDIR="$HOME/.local/state/ssm"

mkdir -p "$STATEDIR"

echo "$SLURM_SUBMIT_DIR" > "$STATEDIR/$SLURM_JOB_ID"

# vim: set shiftwidth=4 expandtab:
