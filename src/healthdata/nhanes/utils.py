from pathlib import Path


def resolve_local_file(path: str) -> str:
	"""Resolve a filename spelling on different types of filesystems"""
	candidate = Path(path)
	if not candidate.parent.is_dir():
		return str(candidate)

	matches = []
	for entry in candidate.parent.iterdir():
		if not entry.is_file():
			continue
		if entry.name == candidate.name:
			return str(entry)
		if entry.name.casefold() == candidate.name.casefold():
			matches.append(entry)

	if len(matches) == 1:
		return str(matches[0])
	return str(candidate)