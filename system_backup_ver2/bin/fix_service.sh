#!/bin/bash
sudo sed -i 's/^CPUSchedulingPolicy=rr/#CPUSchedulingPolicy=rr/' /etc/systemd/system/run_sox_fifo.service
sudo sed -i 's/^CPUSchedulingPriority=48/#CPUSchedulingPriority=48/' /etc/systemd/system/run_sox_fifo.service
sudo sed -i 's/^OOMScoreAdjust=-999/#OOMScoreAdjust=-999/' /etc/systemd/system/run_sox_fifo.service
sudo systemctl daemon-reload
sudo systemctl restart run_sox_fifo.service
echo "Done!"
