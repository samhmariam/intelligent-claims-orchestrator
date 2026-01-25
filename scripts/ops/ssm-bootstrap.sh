#!/bin/bash
yum install -y amazon-ssm-agent
systemctl enable amazon-ssm-agent
systemctl restart amazon-ssm-agent
