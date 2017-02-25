#!/bin/python3
# this file runs within the firejailed and pagsh'd environment.
# it authenticates to afs with aklog.
# all communication with the outside world is done through stdio.
import json
import os
import tempfile
import traceback
import base64
import sys
import kerberos
import subprocess

def run_aklog(ccache):
	with tempfile.NamedTemporaryFile(prefix="webafs_ccache_") as tempf:
		tempf.write(ccache)
		tempf.flush()
		aklog_out = subprocess.call(["aklog"], timeout=20, env={"KRB5CCNAME": tempf.name}, stdout=sys.stderr) == 0
	return aklog_out

for line in sys.stdin:
	line = line.encode() # TODO: get binary data directly? and maybe switch to a binary protocol
	out = (b"FAIL", b"NO_OUTPUT")
	if line.count(b" ") != 2:
		seqno = b"--"
		out = (b"FAIL", b"MALFORMED_COMMAND")
	else:
		seqno, command, argument = line.split(b" ", 2)
		try:
			if command == b"AUTH":
				found_data = kerberos.parse(base64.b64decode(argument))
				if found_data:
					try:
						if run_aklog(found_data[1]):
							out = (b"ACCEPT_AUTH", b"")
						else:
							out = (b"FAIL", b"AKLOG_FAILED")
					except subprocess.TimeoutExpired:
						out = (b"FAIL", b"AKLOG_TIMEOUT")
				else:
					out = (b"FAIL", b"MALFORMED_TICKET")
			elif command == b"FETCH":
				# TODO: make sure this code actually works for isolation
				path = base64.b64decode(argument).decode()
				if ".." in path:
					out = (b"FAIL", b"DISALLOWED_PATH")
				else:
					path = "/afs/" + path
					try:
						with open(path, "rb") as f:
							out = (b"FILEDATA", base64.b64encode(f.read()))
					except FileNotFoundError:
						out = (b"NOEXIST", b"")
					except PermissionError:
						out = (b"NOPERM", b"")
			elif command == b"LIST":
				# TODO: make sure this code actually works for isolation
				path = base64.b64decode(argument).decode()
				if ".." in path:
					out = (b"FAIL", b"DISALLOWED_PATH")
				else:
					path = "/afs/" + path
					try:
						out = (b"LISTDATA", base64.b64encode(json.dumps(os.listdir(path)).encode()))
					except FileNotFoundError:
						out = (b"NOEXIST", b"")
					except PermissionError:
						out = (b"NOPERM", b"")
					except NotADirectoryError:
						out = (b"NOTDIR", b"")
			else:
				out = (b"FAIL", b"INVALID_COMMAND")
		except:
			traceback.print_exc()
			out = (b"FAIL", b"INTERNAL_ERROR")
	if b" " in out[0] or b" " in out[1] or b"\n" in out[0] or b"\n" in out[1] or len(out) != 2:
		print("internal error details:", out, file=sys.stderr)
		out = (b"FAIL", b"INTERNAL_ERROR_2")
	out = b" ".join((seqno, out[0], out[1]))
	assert out.count(b" ") == 2 and out.count(b"\n") == 0
	sys.stdout.buffer.write(out + b"\n")
	sys.stdout.buffer.flush()
print("finished reading", file=sys.stderr)
