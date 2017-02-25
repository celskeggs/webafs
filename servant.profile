include /etc/firejail/default.profile
include /etc/firejail/disable-common.inc
include /etc/firejail/disable-programs.inc
include /etc/firejail/disable-passwdmgr.inc

blacklist /home
blacklist /srv
blacklist /var
blacklist /boot
blacklist /media
blacklist /mnt
blacklist /root
blacklist /run
blacklist /sys
whitelist /opt/webafs/inside/
read-only /opt/webafs/inside/
name afscli
netfilter
private
private-dev
private-tmp
read-only /
tracelog
shell none
nosound
no3d
caps.drop all
seccomp
nonewprivs
noroot
# x11 none # TODO re-enable
ipc-namespace
hostname anonymous-afs
