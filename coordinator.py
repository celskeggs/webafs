#!/usr/bin/env python3.6
# this file runs outside and provides a connection to the servant environment
import traceback
import subprocess
import os
import socket
import time
import sys

if len(sys.argv) != 2:
	print("Usage: python3.6 coordinator.py (ID)")
	sys.exit(1)
coordinator_id = sys.argv[1]
if not coordinator_id.isalnum():
	print("Expected an alphanumeric string.")
	sys.exit(1)

subprocess_current = None

def subprocess_interact(command):
	assert type(command) == bytes
	global subprocess_current
	if subprocess_current is not None and subprocess_current.poll() is not None:
		print("RESTARTING PROCESS AFTER COOLDOWN")
		time.sleep(10)
		subprocess_current = None
	if subprocess_current is None:
		subprocess_current = subprocess.Popen(["pagsh", "-c", "firejail --quiet --profile=servant.profile /usr/bin/env python3.6 /opt/webafs/inside/servant.py"], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
		time.sleep(0.5)
		if subprocess_current.poll() is not None:
			subprocess_current = None
			return b"-- FAIL SUBPROCESS_ERROR\n"
	if b"\n" in command:
		return b"-- FAIL SUBPROCESS_ERROR\n"
	else:
		subprocess_current.stdin.write(command + b"\n")
		subprocess_current.stdin.flush()
		outline = subprocess_current.stdout.readline()
		return outline

server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
spath = "/opt/webafs/coordinator/%s" % coordinator_id
server.bind(spath)
try:
	server.listen(10)

	last_conn = time.time()
	server.settimeout(5)
	while time.time() - last_conn < 3600 and os.path.exists(spath): # last for an hour before timing out and closing
		try:
			conn, addr = server.accept()
		except socket.timeout:
			continue
		try:
			last_conn = time.time()
			conn.settimeout(5)
			buffered = b""
			while b"\n" not in buffered:
				received = conn.recv(4096)
				if not received:
					raise socket.timeout()
				buffered += received
			# failed asserts will trigger exception machinery and close the connection immediately
			assert buffered[-1] == 10 and buffered.count(b"\n") == 1, "buffered: %s" % buffered
			buffered = buffered[:-1]
			assert buffered.count(b" ") == 2 and b"\n" not in buffered
			fetched_data = subprocess_interact(buffered)
			assert fetched_data.count(b"\n") == 1 and fetched_data[-1] == 10
			conn.sendall(fetched_data)
		except KeyboardInterrupt as e:
			raise e
		except Exception as e:
			traceback.print_exc()
		finally:
			try:
				conn.close()
			except:
				pass
except socket.timeout:
	print("Timed out. Dying.")
finally:
	try:
		server.close()
	finally:
		os.unlink(spath)
