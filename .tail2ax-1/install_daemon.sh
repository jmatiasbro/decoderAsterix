#!/usr/bin/env bash

sudo cp ./shutdown_tail2ax.service /etc/systemd/system/
sudo systemctl enable shutdown_tail2ax
