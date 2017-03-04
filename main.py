import cherrypy
import json
import os
import sys
import uuid
import base64
import traceback
import binascii
import time
import threading
import hmac
import socket

# ---- start coordinator handling ----

COORD_DIR = "/opt/webafs/coordinator"
IOSOCK_PATH = "/opt/webafs/iodir/iosock"
found_any = False
# close out lingering coordinators
# TODO: reuse existing coordinators?
for x in os.listdir(COORD_DIR):
	found_any = True
	os.unlink(os.path.join(COORD_DIR, x))
if found_any:
	time.sleep(15) # give the coordinators time to exit

coordinators = {}
coord_lock = threading.Condition()

class Coordinator(object):
	def __init__(self, coord_uuid):
		assert type(coord_uuid) == uuid.UUID
		self.uuid = coord_uuid
		self.cid = str(coord_uuid).replace("-", "")
		os.system("python3.6 coordinator.py %s &" % self.cid)
		self.path = "%s/%s" % (COORD_DIR, self.cid)
		i = 50
		while not os.path.exists(self.path) and i > 0:
			time.sleep(0.1)
			i -= 1

	def isalive(self):
		return os.path.exists(self.path)

	def interact(self, command, argument):
		assert b" " not in command and b" " not in argument and b"\n" not in command and b"\n" not in argument
		request = (base64.b64encode(os.urandom(8)), command, argument)
		s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
		try:
			s.connect(self.path)
			s.sendall(b" ".join(request) + b"\n")
			buffered = b""
			while b"\n" not in buffered:
				received = s.recv(4096)
				if not received:
					return False, b"TRUNCATED_RECV", None
				buffered += received
			if buffered.endswith(b"\n") and buffered.count(b"\n") == 1 and buffered.count(b" ") == 2:
				request_id, code, param = buffered.split(b" ")
				if request_id == request[0]:
					return True, code, param
				elif request_id == b"--" and code == b"FAIL":
					return False, param, None
				else:
					return False, b"INTERNAL_ID_MISMATCH", None
			else:
				return False, b"INTERNAL_MALFORMED_DATA", None
		except Exception as e:
			traceback.print_exc()
			return False, b"INTERNAL_EXCEPTION", None
		finally:
			s.close()

def new_coordinator():
	coord_uuid = uuid.uuid4()
	with coord_lock:
		assert coord_uuid not in coordinators
		coordinators[coord_uuid] = None
		# while we're at it, scan for lingering dead coordinators
		to_drop = []
		for coord in coordinators.values():
			if coord is not None and not coord.isalive():
				to_drop.append(coord.uuid)
				cleanup_client_context(coord.uuid)
		for drop in to_drop:
			del coordinators[drop]
	coord = Coordinator(coord_uuid)
	with coord_lock:
		assert coordinators[coord_uuid] is None
		coordinators[coord_uuid] = coord
	return coord_uuid

def get_coordinator(coord_uuid):
	with coord_lock:
		return coordinators.get(coord_uuid, None)

def interact(coord_uuid, command, argument):
	assert type(coord_uuid) == uuid.UUID
	coord = get_coordinator(coord_uuid)
	if coord is None:
		return False, b"MISSING_COORDINATOR", None
	else:
		return coord.interact(command, argument)

# main web code

access_tokens = {}
access_token_lock = threading.Lock()

def new_client_context():
	coord_uuid = new_coordinator()
	with access_token_lock:
		assert coord_uuid not in access_tokens
		token = os.urandom(64)
		access_tokens[coord_uuid] = token
	return coord_uuid, token

def interact_auth(coord_uuid, auth_cred):
	success, code, param = interact(coord_uuid, b"AUTH", auth_cred)
	if not success:
		param = code
		code = b"FAIL"
	return code, param

def interact_fetch(coord_uuid, postafs_path):
	success, code, param = interact(coord_uuid, b"FETCH", postafs_path)
	if not success:
		param = code
		code = b"FAIL"
	return code, param

def interact_list(coord_uuid, postafs_path):
	success, code, param = interact(coord_uuid, b"LIST", postafs_path)
	if not success:
		param = code
		code = b"FAIL"
	return code, param

def interact_reflocker(coord_uuid, lockername):
	success, code, param = interact(coord_uuid, b"REFLOCKER", lockername)
	if not success:
		param = code
		code = b"FAIL"
	return code, param

def cleanup_client_context(coord_uuid):
	del access_tokens[coord_uuid]

class WebAFS(object):
	@cherrypy.expose
	@cherrypy.tools.json_out()
	def begin(self):
		coord_uuid, access_token = new_client_context()
		return {"session": str(coord_uuid), "token": base64.b64encode(access_token).decode()}

	def _check_token(self):
		coord_uuid = cherrypy.request.json.get("session", None)
		access_token = cherrypy.request.json.get("token", None)
		if access_token is None or coord_uuid is None:
			return False, {"status": "FAIL", "param": "INVALID_AUTH"}
		try:
			access_token = base64.b64decode(access_token)
		except binascii.Error:
			code, param = {"status": "FAIL", "param": "INVALID_AUTH"}
		try:
			coord_uuid = uuid.UUID(coord_uuid)
		except ValueError:
			return False, {"status": "FAIL", "param": "INVALID_AUTH"}
		expected = access_tokens.get(coord_uuid, None)
		if expected is None:
			return False, {"status": "FAIL", "param": "UNKNOWN_UUID"}
		if hmac.compare_digest(access_token, expected):
			return True, coord_uuid
		else:
			return False, {"status": "FAIL", "param": "INVALID_AUTH"}

	@cherrypy.expose
	@cherrypy.tools.json_in()
	@cherrypy.tools.json_out()
	def auth(self):
		success, data = self._check_token()
		if not success: return data
		cred = cherrypy.request.json.get("cred", None)
		if cred is None:
			code, param = b"FAIL", b"INVALID_INPUTS"
		else:
			code, param = interact_auth(data, base64.b64encode(cred.encode()))
		return {"status": code.decode(), "param": param.decode()}

	@cherrypy.expose
	@cherrypy.tools.json_in()
	@cherrypy.tools.json_out()
	def fetch(self):
		success, data = self._check_token()
		if not success: return data
		path = cherrypy.request.json.get("path", None)
		if path is None:
			code, param = b"FAIL", b"INVALID_INPUTS"
		else:
			code, param = interact_fetch(data, base64.b64encode(path.encode()))
		return {"status": code.decode(), "param": param.decode()}

	@cherrypy.expose
	@cherrypy.tools.json_in()
	@cherrypy.tools.json_out()
	def list(self):
		success, data = self._check_token()
		if not success: return data
		path = cherrypy.request.json.get("path", None)
		if path is None:
			code, param = b"FAIL", b"INVALID_INPUTS"
		else:
			code, param = interact_list(data, base64.b64encode(path.encode()))
		return {"status": code.decode(), "param": param.decode()}

	@cherrypy.expose
	@cherrypy.tools.json_in()
	@cherrypy.tools.json_out()
	def reflocker(self):
		success, data = self._check_token()
		if not success: return data
		locker = cherrypy.request.json.get("locker", None)
		if locker is None:
			code, param = b"FAIL", b"INVALID_INPUTS"
		else:
			code, param = interact_reflocker(data, base64.b64encode(locker.encode()))
		return {"status": code.decode(), "param": param.decode()}

try:
	os.unlink(IOSOCK_PATH)
except:
	pass
os.chmod(os.path.dirname(IOSOCK_PATH), 0o0750)
cherrypy.engine.subscribe("start", lambda: os.chmod(IOSOCK_PATH, 0o0777), priority=90)
cherrypy.config.update({'environment': 'production', 'server.socket_file': IOSOCK_PATH, 'log.screen': True})
cherrypy.quickstart(WebAFS(), "/", {"/": {"tools.staticdir.on": True, "tools.staticdir.dir": "/opt/webafs/static", "tools.staticdir.index": "index.html"}})
