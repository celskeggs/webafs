import os
import stat
import sys

# DO NOT USE THIS MODULE MULTITHREADED!

ROOT = "/afs"
LOCKER_ROOT = "/mit"

class PathFD:
	def __init__(self, fd):
		assert type(fd) is int
		self.fd = fd

	_root_cache = None

	@staticmethod
	def root():
		if PathFD._root_cache is None:
			PathFD._root_cache = PathFD(os.open(ROOT, os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOCTTY | os.O_NOFOLLOW | os.O_PATH))
		return PathFD._root_cache

	def directory(self, dirname):
		assert self.fd is not None
		assert dirname not in (".", "..") and "/" not in dirname
		return PathFD(os.open(dirname, os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOCTTY | os.O_NOFOLLOW | os.O_PATH, dir_fd = self.fd))

	def openfile(self, filename):
		assert self.fd is not None
		assert filename not in (".", "..") and "/" not in filename
		fd = os.open(filename, os.O_RDONLY | os.O_CLOEXEC | os.O_NOCTTY | os.O_NOFOLLOW, dir_fd = self.fd)
		try:
			return open(fd, "rb")
		except:
			os.close(fd)

	def listfiles(self):
		assert self.fd is not None
		local_fd = os.open(".", os.O_RDONLY | os.O_CLOEXEC | os.O_NOCTTY | os.O_NOFOLLOW, dir_fd=self.fd)
		try:
			assert type(local_fd) == int
			return os.scandir("/proc/self/fd/%d" % local_fd)
		finally:
			os.close(local_fd)

	def isdir(self, subdir):
		assert self.fd is not None
		try:
			os.close(os.open(subdir, os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOCTTY | os.O_NOFOLLOW | os.O_PATH, dir_fd = self.fd))
		except PermissionError:
			return False  # not a directory -- you can stat directories even if you don't have access
		except NotADirectoryError:
			return False  # also not a directory
		return True # otherwise? since it was O_DIRECTORY, probably a directory.

	def close(self):
		if type(self.fd) is int:
			os.close(self.fd)
			self.fd = None
			return True
		else:
			assert self.fd is None
			return False

	def __del__(self):
		if self.fd is not None:
			# print("WARNING: PathFD was not closed!", file=sys.stderr)
			self.close()

def split_components(path):
	spt = []
	while "/" in path:
		path, elem = os.path.split(path)
		if path == "/":
			path = elem
			continue
		if elem:
			spt.append(elem)
	spt.append(path)
	return spt[::-1]

def traverse(path):
	location = PathFD.root()
	for component in split_components(path):
		if not component:
			continue
		elif component == ".":
			continue
		elif component == "..":
			raise FileNotFoundError("Cannot traverse upward!")
		else:
			location = location.directory(component)
	return location

# these all start at /afs
def safe_list(path):
	print("started listing", path, file=sys.stderr)
	try:
		base = traverse(path)
		with base.listfiles() as files:
			return [(file.name + "/" if file.is_dir(follow_symlinks=False) else file.name) for file in files]
	finally:
		print("finished listing", path, file=sys.stderr)

def safe_load(path):
	path, filename = os.path.split(path)
	with traverse(path).openfile(filename) as f:
		return f.read()

def safe_readlocker(lockername):
	if "/" in lockername or lockername[0] == ".":
		return None
	else:
		try:
			return os.readlink("%s/%s" % (LOCKER_ROOT, lockername))
		except FileNotFoundError:
			return None
