#!/bin/bash -e

mkdir -p /opt/webafs/inside
rm -rf /opt/webafs/coordinator
mkdir -p /opt/webafs/coordinator
chmod 700 /opt/webafs/coordinator
cp main.py coordinator.py servant.profile /opt/webafs/
cp -R static /opt/webafs/
cp kerberos.py servant.py safe_traverse.py /opt/webafs/inside
