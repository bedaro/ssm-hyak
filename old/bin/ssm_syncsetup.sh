#!/bin/sh

case "$1" in
    install)
        mkdir -p $HOME/.config/systemd/user
        cp /gscratch/brett/ssm/systemd/ssm_sync_jobs.* $HOME/.config/systemd/user/
        systemctl --user daemon-reload
        systemctl --user enable --now ssm_sync_jobs.timer
        ;;
    uninstall)
        systemctl --user disable --now ssm_sync_jobs.timer
        ;;
esac

# vim: set shiftwidth=4 expandtab:
