#!/bin/bash
# Simple script that looks for jobs that were registered with ssm_register_job and
# syncs their state to a remote server. Meant to be called on a systemd timer.

STATEDIR="$HOME/.local/state/ssm"

[ -d "$STATEDIR" ] || exit 0

SYNC_COUNT=0

is_remote_path() {
    echo $1 | egrep -q '^[^/]+:.*'
    return $?
}
remote_part() {
    echo $1 | awk -F: '{ print $1 }'
}
local_part() {
    echo $1 | awk -F: '{ print $2 }'
}

do_sync() {
    (
        set -x
        cd "$1"
        rsync -az --exclude OUTPUT --exclude=outputs ./ "$2"
        if [ -d OUTPUT ]; then
            rsync -az --append-verify OUTPUT/ "$2/OUTPUT"
        elif [ -d outputs ]; then
            rsync -az --exclude="ssm_history_*" outputs/ "$2/outputs"
            hist_files=( outputs/ssm_history_* )
            [ -f "${hist_files[0]}" ] && rsync -az --append-verify ${hist_files[*]} "$2/outputs"
        fi
        set +x
    )
    let SYNC_COUNT++
}

job_running() {
    squeue --job $1 &> /dev/null
    return $?
}

echo "Syncing jobs..."
for f in "$STATEDIR/"*; do
    jobid="$(basename $f)"
    jobdir="$(head -1 $f)"
    if [ ! -d "$jobdir" ]; then
        echo "Found nonexistent jobdir $jobdir from $jobid"
        rm "$f"
    fi
    source "$jobdir/batch.rc"
    if ! is_remote_path "$save_root"; then
        continue
    fi
    run_tail="${jobdir##$run_root/}"
    copy_dest="$save_root/$run_tail"
    ssh `remote_part "$copy_dest"` mkdir -p `local_part "$copy_dest"`
    if job_running "$jobid"; then
        echo "Syncing running job $jobid in $jobdir"
        do_sync "$jobdir" "$copy_dest"
    fi
    if ! job_running "$jobid"; then
        echo "Syncing completed job $jobid in $jobdir"
        do_sync "$jobdir" "$copy_dest" final
        rm "$f"
    fi
done
echo "Check complete, $SYNC_COUNT jobs synced"

# vim: set shiftwidth=4 expandtab:
