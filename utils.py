import os


def iter_lines(fd, chunk_size=1024):
    '''Iterates over the content of a file-like object line-by-line.'''

    pending = None

    while True:
        chunk = os.read(fd.fileno(), chunk_size)
        if not chunk:
            break

        if pending is not None:
            chunk = pending + chunk
            pending = None

        lines = chunk.splitlines()

        if lines and lines[-1]:
            pending = lines.pop()

        for line in lines:
            yield line

    if pending:
        yield(pending)
