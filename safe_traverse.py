import os
import sys

# DO NOT USE THIS MODULE MULTITHREADED!

ROOT = "/afs"

class PathFD:
	def __init__(self, fd):
		assert type(fd) is int
		self.fd = fd
		self.cache = {}

	_root_cache = None

	@staticmethod
	def root():
		if PathFD._root_cache is None:
			PathFD._root_cache = PathFD(os.open(ROOT, os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOCTTY | os.O_NOFOLLOW | os.O_PATH))
		print("ROOT")
		return PathFD._root_cache

	def directory(self, dirname):
		print("DIRECTORY", dirname)
		assert self.fd is not None
		assert dirname not in (".", "..") and "/" not in dirname
		if dirname not in self.cache:
			self.cache[dirname] = PathFD(os.open(dirname, os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOCTTY | os.O_NOFOLLOW | os.O_PATH, dir_fd = self.fd))
		return self.cache[dirname]

	def openfile(self, filename):
		print("FILE", filename)
		assert self.fd is not None
		assert filename not in (".", "..") and "/" not in filename
		fd = os.open(filename, os.O_RDONLY | os.O_CLOEXEC | os.O_NOCTTY | os.O_NOFOLLOW, dir_fd = self.fd)
		try:
			return open(fd, "rb")
		except:
			print("Closing fd (2):", fd)
			os.close(fd)

	def listfiles(self):
		print("LIST")
		assert self.fd is not None
		local_fd = os.open(".", os.O_RDONLY | os.O_CLOEXEC | os.O_NOCTTY | os.O_NOFOLLOW, dir_fd=self.fd)
		try:
			return os.listdir(local_fd)
		finally:
			os.close(local_fd)

	def close(self):
		if self.cache:
			for elem in self.cache.values():
				elem.close()
		if type(self.fd) is int:
			os.close(self.fd)
			self.fd = None
			self.cache = None
			return True
		else:
			assert self.fd is None
			assert not self.cache
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
		if component == ".":
			continue
		elif component == "..":
			raise FileNotFoundError("Cannot traverse upward!")
		else:
			location = location.directory(component)
	return location

# these all start at /afs
def safe_list(path):
	return traverse(path).listfiles()

def safe_load(path):
	path, filename = os.path.split(path)
	with traverse(path).openfile(filename) as f:
		return f.read()
